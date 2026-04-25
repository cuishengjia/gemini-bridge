"""Regression tests for the 2026-04-25 pre-public-release security hardening.

Locks in four findings raised by the open-source security review:

  H1  GEMINI_BIN pointing into world-writable temp locations is rejected.
      Override available via ASK_GEMINI_BIN_UNRESTRICTED=1.
  H2  --persist-to refuses to follow a pre-existing symlink at the target,
      closing the symlink-after-parent-validation gap.
  M1  preflight rejects --target-dir when it resolves to a system root or
      $HOME, preventing those paths from being written into
      ~/.gemini/trustedFolders.json.
  M2  Audit log can be told to redact the response body via
      ASK_GEMINI_NO_LOG_RESPONSE=1, while the stdout envelope is unchanged.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path

import pytest


SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from lib import invoke as inv  # noqa: E402
from lib import persist  # noqa: E402
from lib import preflight  # noqa: E402


def _load_bin_module():
    """bin/ask-gemini has no .py suffix; load it explicitly so we can test
    `_audit_payload` without spawning a subprocess."""
    bin_path = SKILL_DIR / "bin" / "ask-gemini"
    loader = importlib.machinery.SourceFileLoader("ask_gemini_cli_bin", str(bin_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# H1: GEMINI_BIN path validation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("danger_path", [
    "/tmp/evil-gemini",
    "/var/tmp/evil-gemini",
    "/private/tmp/evil-gemini",
    "/private/var/tmp/evil-gemini",
])
def test_gemini_bin_in_world_writable_temp_is_rejected(monkeypatch, danger_path):
    """A `gemini` binary pointed at /tmp etc. must not be invoked: those
    locations are world-writable and a classic local-privesc target."""
    monkeypatch.setenv("GEMINI_BIN", danger_path)
    monkeypatch.delenv("ASK_GEMINI_BIN_UNRESTRICTED", raising=False)
    with pytest.raises(inv.SafetyAssertionError, match="world-writable"):
        inv.gemini_bin()


def test_gemini_bin_unrestricted_env_disables_check(monkeypatch):
    """Operators with a legitimate edge case can opt out of the path screen.
    The env var name is intentionally verbose so it leaves an audit trail."""
    monkeypatch.setenv("GEMINI_BIN", "/tmp/legitimate-but-unusual-gemini")
    monkeypatch.setenv("ASK_GEMINI_BIN_UNRESTRICTED", "1")
    assert inv.gemini_bin() == "/tmp/legitimate-but-unusual-gemini"


def test_gemini_bin_normal_path_still_works(monkeypatch):
    """Regression guard: the validation must not break legitimate overrides
    (npm install paths, custom forks, /opt installs, etc.)."""
    monkeypatch.setenv("GEMINI_BIN", "/usr/local/bin/gemini")
    monkeypatch.delenv("ASK_GEMINI_BIN_UNRESTRICTED", raising=False)
    assert inv.gemini_bin() == "/usr/local/bin/gemini"


# --------------------------------------------------------------------------- #
# H2: --persist-to symlink refusal
# --------------------------------------------------------------------------- #

def test_persist_to_symlink_target_is_rejected(tmp_path, monkeypatch):
    """If `target` is itself a symlink, parent.resolve() leaves a window
    where a write follows the symlink to wherever it points. Refuse early."""
    monkeypatch.setenv("HOME", str(tmp_path))
    real_dir = tmp_path / "out"
    real_dir.mkdir()
    legit_target = real_dir / "real.md"
    legit_target.write_text("placeholder", encoding="utf-8")

    symlink_target = real_dir / "link.md"
    symlink_target.symlink_to(legit_target)

    with pytest.raises(ValueError, match="symlink"):
        persist._validate_persist_target(symlink_target)


def test_persist_response_refuses_symlink_target(tmp_path, monkeypatch):
    """End-to-end check: persist_response must not write through a symlink."""
    monkeypatch.setenv("HOME", str(tmp_path))
    real = tmp_path / "real.md"
    real.write_text("untouched", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(real)

    with pytest.raises(ValueError, match="symlink"):
        persist.persist_response(
            target=link, mode="analyze", prompt="p", response="EVIL",
            model_used="m",
        )

    # The file behind the symlink must remain untouched.
    assert real.read_text(encoding="utf-8") == "untouched"


# --------------------------------------------------------------------------- #
# M1: preflight rejects overly broad --target-dir
# --------------------------------------------------------------------------- #

def test_check_trust_target_rejects_filesystem_root():
    """Auto-trusting `/` would persist a wildcard scope into trustedFolders."""
    err = preflight._check_trust_target(Path("/"))
    assert err is not None
    assert err.error_kind == "bad_input"
    assert "too broad" in err.error_message


@pytest.mark.parametrize("system_path", ["/etc", "/usr", "/var", "/opt"])
def test_check_trust_target_rejects_system_directories(system_path):
    err = preflight._check_trust_target(Path(system_path))
    assert err is not None
    assert err.error_kind == "bad_input"


def test_check_trust_target_rejects_home_itself(tmp_path, monkeypatch):
    """$HOME is too broad — pass a project subdir, not the whole home."""
    monkeypatch.setenv("HOME", str(tmp_path))
    err = preflight._check_trust_target(tmp_path)
    assert err is not None
    assert err.error_kind == "bad_input"
    assert "HOME" in err.error_message or "broad" in err.error_message


def test_check_trust_target_accepts_normal_subdir(tmp_path, monkeypatch):
    """Project subdirectory under $HOME (the common case) must still pass."""
    monkeypatch.setenv("HOME", str(tmp_path))
    project = tmp_path / "myproject"
    project.mkdir()
    err = preflight._check_trust_target(project)
    assert err is None


# --------------------------------------------------------------------------- #
# M2: ASK_GEMINI_NO_LOG_RESPONSE redacts audit log payload
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def ask_gemini_module():
    return _load_bin_module()


def test_audit_payload_unredacted_by_default(ask_gemini_module, monkeypatch):
    monkeypatch.delenv("ASK_GEMINI_NO_LOG_RESPONSE", raising=False)
    env = {
        "ok": True,
        "mode": "research",
        "response": "secret model output",
        "tool_calls": [{"name": "google_search", "query": "private query"}],
    }
    out = ask_gemini_module._audit_payload(env)
    assert out is env  # unchanged identity by default
    assert out["response"] == "secret model output"
    assert out["tool_calls"][0]["query"] == "private query"


def test_audit_payload_redacts_when_env_set(ask_gemini_module, monkeypatch):
    """When opted in, the audit log gets metadata only — response and
    tool_calls are stripped. The caller's stdout envelope is unaffected
    (this fixture only exercises the audit-log branch)."""
    monkeypatch.setenv("ASK_GEMINI_NO_LOG_RESPONSE", "1")
    env = {
        "ok": True,
        "mode": "research",
        "response": "secret model output",
        "tool_calls": [{"name": "google_search", "query": "private query"}],
        "stats": {"total_tokens": 123},
    }
    out = ask_gemini_module._audit_payload(env)
    assert out is not env
    assert out["response"] == "<redacted by ASK_GEMINI_NO_LOG_RESPONSE>"
    assert out["tool_calls"] == []
    # Metadata must survive: that's the whole point of keeping the log.
    assert out["stats"] == {"total_tokens": 123}
    assert out["mode"] == "research"
    assert out["ok"] is True

    # The original env dict must NOT have been mutated; the caller still
    # receives the full envelope on stdout.
    assert env["response"] == "secret model output"
    assert env["tool_calls"][0]["query"] == "private query"
