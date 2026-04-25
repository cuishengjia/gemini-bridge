"""Unit tests for lib.audit_log (best-effort JSONL writer with rotation)."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from lib import audit_log  # noqa: E402


def test_first_write_creates_file_and_directory(tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "cache-root"
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(cache))

    audit_log.append({"event": "first", "mode": "analyze"})

    logfile = cache / "invocations.jsonl"
    assert logfile.exists()
    lines = logfile.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "first"


def test_append_preserves_previous_lines(tmp_path: Path,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(tmp_path))

    audit_log.append({"n": 1})
    audit_log.append({"n": 2})
    audit_log.append({"n": 3})

    lines = (tmp_path / "invocations.jsonl").read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [p["n"] for p in parsed] == [1, 2, 3]


def test_rotation_at_size_threshold(tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(tmp_path))
    # Shrink the limit for test speed; the contract is "≥ limit triggers rotation".
    monkeypatch.setattr(audit_log, "LOG_SIZE_LIMIT_BYTES", 100)

    logfile = tmp_path / "invocations.jsonl"
    logfile.write_text("x" * 500, encoding="utf-8")

    audit_log.append({"event": "after-rotation"})

    rotated = tmp_path / "invocations.1.jsonl"
    assert rotated.exists()
    assert logfile.exists()

    # The active file should only contain the new event.
    active_lines = logfile.read_text(encoding="utf-8").splitlines()
    assert len(active_lines) == 1
    assert json.loads(active_lines[0])["event"] == "after-rotation"


def test_rotation_overwrites_existing_rotated_file(tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(audit_log, "LOG_SIZE_LIMIT_BYTES", 50)

    logfile = tmp_path / "invocations.jsonl"
    rotated = tmp_path / "invocations.1.jsonl"
    logfile.write_text("a" * 200, encoding="utf-8")
    rotated.write_text("STALE", encoding="utf-8")

    audit_log.append({"event": "new"})

    assert "STALE" not in rotated.read_text(encoding="utf-8")


def test_append_never_raises_on_bad_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    # Use an impossible path and ensure no exception propagates.
    bad = Path("/dev/null/impossible/ask-gemini-cli-cache")
    monkeypatch.setattr(audit_log, "log_dir", lambda: bad)
    monkeypatch.setattr(audit_log, "log_file", lambda: bad / "invocations.jsonl")

    # Must not raise.
    audit_log.append({"event": "should-not-raise"})


def test_append_never_raises_on_unserializable_event(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(tmp_path))
    # Object that cannot be JSON-serialized.

    class NotSerializable:
        pass

    audit_log.append({"bad": NotSerializable()})  # must not raise
    # Fallback record should still appear.
    logfile = tmp_path / "invocations.jsonl"
    assert logfile.exists()
    content = logfile.read_text(encoding="utf-8")
    assert "unserializable" in content


# --------------------------------------------------------------------------- #
# Path helpers and edge cases
# --------------------------------------------------------------------------- #

def test_log_dir_override_via_env(monkeypatch: pytest.MonkeyPatch,
                                  tmp_path: Path) -> None:
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(tmp_path / "custom"))
    assert audit_log.log_dir() == tmp_path / "custom"


def test_log_dir_default_is_home_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASK_GEMINI_CACHE_DIR", raising=False)
    result = audit_log.log_dir()
    assert result.parts[-2:] == (".cache", "ask-gemini-cli")


def test_log_file_is_invocations_jsonl(monkeypatch: pytest.MonkeyPatch,
                                       tmp_path: Path) -> None:
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(tmp_path))
    assert audit_log.log_file() == tmp_path / "invocations.jsonl"


def test_rotate_if_missing_file_is_noop(tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """_rotate_if_needed should silently return when the file doesn't exist."""
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(tmp_path))
    audit_log._rotate_if_needed(tmp_path / "does-not-exist.jsonl")
    # No exception, no file created.
    assert not (tmp_path / "invocations.1.jsonl").exists()


def test_rotate_if_rotated_unlink_fails_still_rotates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even if unlinking the stale rotated file fails, rename should still be attempted."""
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(audit_log, "LOG_SIZE_LIMIT_BYTES", 10)

    logfile = tmp_path / "invocations.jsonl"
    logfile.write_text("x" * 50)

    # Simulate an unlink failure on the rotated file.
    original_unlink = Path.unlink

    def flaky_unlink(self, *a, **kw):
        if self.name == "invocations.1.jsonl":
            raise OSError("pretend permission denied")
        return original_unlink(self, *a, **kw)

    rotated = tmp_path / "invocations.1.jsonl"
    rotated.write_text("STALE")
    monkeypatch.setattr(Path, "unlink", flaky_unlink)

    # Must not raise.
    audit_log.append({"event": "x"})


# --------------------------------------------------------------------------- #
# H4: file permissions (0600) and directory permissions (0700)
# --------------------------------------------------------------------------- #

def test_append_sets_file_mode_0600(tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """The log file must be user-rw-only (0600). Audit content may include
    prompts or paths; world/group readability would be a disclosure bug.
    """
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(tmp_path))

    assert audit_log.append({"event": "perm-check"}) is None

    logfile = tmp_path / "invocations.jsonl"
    mode = stat.S_IMODE(logfile.stat().st_mode)
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


def test_append_sets_dir_mode_0700(tmp_path: Path,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """The cache directory itself should be user-only (0700)."""
    cache = tmp_path / "fresh"
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(cache))

    audit_log.append({"event": "dir-perm"})

    mode = stat.S_IMODE(cache.stat().st_mode)
    assert mode == 0o700, f"expected 0700, got {oct(mode)}"


# --------------------------------------------------------------------------- #
# M8: Optional[str] return contract — success returns None, failure returns str
# --------------------------------------------------------------------------- #

def test_append_returns_none_on_success(tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_GEMINI_CACHE_DIR", str(tmp_path))
    assert audit_log.append({"event": "ok"}) is None


def test_append_returns_reason_when_mkdir_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the cache dir can't be created, the caller must get a non-None reason
    string so it can surface the failure via envelope.warnings."""
    # /dev/null cannot hold a directory — mkdir will raise NotADirectoryError.
    monkeypatch.setattr(audit_log, "log_dir", lambda: Path("/dev/null/nope"))
    monkeypatch.setattr(audit_log, "log_file",
                        lambda: Path("/dev/null/nope/invocations.jsonl"))

    reason = audit_log.append({"event": "x"})
    assert isinstance(reason, str)
    assert reason  # non-empty
    # The diagnostic should at least mention the failing stage.
    assert "failed" in reason or "error" in reason
