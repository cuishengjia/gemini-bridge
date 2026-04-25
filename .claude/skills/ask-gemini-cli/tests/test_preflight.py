"""Unit tests for ask-gemini-cli preflight checks.

Covers:
  * Binary / auth / path existence checks
  * Auto-trust of target_dir into ~/.gemini/trustedFolders.json
  * Audit log emission on first trust
  * GCP warning when GOOGLE_CLOUD_PROJECT + GEMINI_API_KEY co-exist
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Locate skill dir: tests/ -> <skill>/
SKILL_DIR = Path(__file__).resolve().parent.parent
LIB_DIR = SKILL_DIR / "lib"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import audit_log  # noqa: E402
import preflight  # noqa: E402
from preflight import run_preflight  # noqa: E402


# ---------- fixtures ----------

@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect HOME so Path.home() -> tmp_path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Path.home() on POSIX consults HOME env var.
    return tmp_path


@pytest.fixture
def fake_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an executable stub and point GEMINI_BIN at it."""
    bin_path = tmp_path / "gemini-stub"
    bin_path.write_text("#!/bin/sh\nexit 0\n")
    bin_path.chmod(bin_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("GEMINI_BIN", str(bin_path))
    return bin_path


@pytest.fixture
def mock_audit(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace audit_log.append with a MagicMock."""
    mock = MagicMock()
    monkeypatch.setattr(audit_log, "append", mock)
    return mock


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip auth + GCP env vars so each test starts clean."""
    for var in ("GEMINI_API_KEY", "GOOGLE_CLOUD_PROJECT"):
        monkeypatch.delenv(var, raising=False)


# ---------- tests ----------

def test_happy_path_api_key_and_target_dir(
    fake_home: Path,
    fake_bin: Path,
    mock_audit: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clean_env: None,
) -> None:
    """API key set + binary exists + target_dir exists -> ok, auto-trusted."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    target = fake_home / "project"
    target.mkdir()

    result = run_preflight(target_dir=target)

    assert result.ok is True
    assert result.error_kind is None
    assert len(result.auto_trusted_dirs) == 1
    assert result.auto_trusted_dirs[0] == str(target.resolve())
    assert preflight.AUTO_TRUST_WARNING in result.warnings
    # trustedFolders.json was written
    tf = fake_home / ".gemini" / "trustedFolders.json"
    assert tf.exists()
    data = json.loads(tf.read_text())
    assert data[str(target.resolve())] == "TRUST_FOLDER"


def test_missing_api_key_and_no_oauth_file(
    fake_home: Path,
    fake_bin: Path,
    mock_audit: MagicMock,
    clean_env: None,
) -> None:
    """No GEMINI_API_KEY and no OAuth cache -> error_kind='auth'."""
    result = run_preflight()

    assert result.ok is False
    assert result.error_kind == "auth"
    assert "GEMINI_API_KEY" in result.setup_hint
    assert "aistudio.google.com" in result.setup_hint


def test_oauth_file_exists_no_api_key(
    fake_home: Path,
    fake_bin: Path,
    mock_audit: MagicMock,
    clean_env: None,
) -> None:
    """OAuth creds file present -> ok=True even without API key."""
    gemini_dir = fake_home / ".gemini"
    gemini_dir.mkdir()
    (gemini_dir / "oauth_creds.json").write_text('{"access_token": "x"}')

    result = run_preflight()

    assert result.ok is True
    assert result.error_kind is None


def test_target_dir_does_not_exist(
    fake_home: Path,
    fake_bin: Path,
    mock_audit: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clean_env: None,
) -> None:
    """Nonexistent target_dir -> error_kind='bad_input'."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    missing = fake_home / "does-not-exist"

    result = run_preflight(target_dir=missing)

    assert result.ok is False
    assert result.error_kind == "bad_input"
    assert "target_dir" in result.error_message
    mock_audit.assert_not_called()


def test_artefact_file_does_not_exist(
    fake_home: Path,
    fake_bin: Path,
    mock_audit: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clean_env: None,
) -> None:
    """Nonexistent artefact_file -> error_kind='bad_input'."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    missing = fake_home / "missing.md"

    result = run_preflight(artefact_file=missing)

    assert result.ok is False
    assert result.error_kind == "bad_input"
    assert "artefact_file" in result.error_message


def test_gemini_bin_not_executable(
    fake_home: Path,
    tmp_path: Path,
    mock_audit: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clean_env: None,
) -> None:
    """Non-executable GEMINI_BIN -> error_kind='config'."""
    bogus = tmp_path / "not-a-binary.txt"
    bogus.write_text("plain text, not executable")
    # explicitly strip exec bits
    bogus.chmod(0o644)
    monkeypatch.setenv("GEMINI_BIN", str(bogus))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    result = run_preflight()

    assert result.ok is False
    assert result.error_kind == "config"
    assert "Gemini CLI" in result.setup_hint


def test_already_trusted_dir_no_event(
    fake_home: Path,
    fake_bin: Path,
    mock_audit: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clean_env: None,
) -> None:
    """Pre-existing trusted entry -> no auto-trust, no audit event, no warning."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    target = fake_home / "project"
    target.mkdir()

    gemini_dir = fake_home / ".gemini"
    gemini_dir.mkdir()
    tf = gemini_dir / "trustedFolders.json"
    tf.write_text(json.dumps({str(target.resolve()): "TRUST_FOLDER"}))

    result = run_preflight(target_dir=target)

    assert result.ok is True
    assert result.auto_trusted_dirs == []
    assert preflight.AUTO_TRUST_WARNING not in result.warnings
    mock_audit.assert_not_called()


def test_gcp_and_api_key_both_set_emits_warning(
    fake_home: Path,
    fake_bin: Path,
    mock_audit: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clean_env: None,
) -> None:
    """GOOGLE_CLOUD_PROJECT + GEMINI_API_KEY together -> GCP warning appended."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-proj")

    result = run_preflight()

    assert result.ok is True
    assert preflight.GCP_WARNING in result.warnings


def test_audit_log_called_exactly_once_on_first_trust(
    fake_home: Path,
    fake_bin: Path,
    mock_audit: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clean_env: None,
) -> None:
    """audit_log.append called exactly once with event='auto_trusted'."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    target = fake_home / "project"
    target.mkdir()

    result = run_preflight(target_dir=target)

    assert result.ok is True
    assert mock_audit.call_count == 1
    (called_arg,), _ = mock_audit.call_args
    assert called_arg["event"] == "auto_trusted"
    assert called_arg["path"] == str(target.resolve())
    assert "ts" in called_arg
    # ts should be ISO8601 UTC (contain 'T' and '+00:00')
    assert "T" in called_arg["ts"]


def test_target_dir_is_file_not_dir(
    fake_home: Path,
    fake_bin: Path,
    mock_audit: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clean_env: None,
) -> None:
    """target_dir pointing at a file -> error_kind='bad_input'."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    f = fake_home / "file.txt"
    f.write_text("hello")

    result = run_preflight(target_dir=f)

    assert result.ok is False
    assert result.error_kind == "bad_input"
    assert "not a directory" in result.error_message
