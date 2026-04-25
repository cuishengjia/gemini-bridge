"""Unit tests for ask-gemini-cli safety invariants.

Covers:
  * build_argv() hardcoded invariants (--approval-mode plan, -o stream-json,
    --policy <path>).
  * SafetyAssertionError on bad inputs.
  * Policy TOML parses and contains the required deny rules.
  * _assert_safety() rejects risky mutated argv.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Locate the skill directory: tests/ -> <skill>/
SKILL_DIR = Path(__file__).resolve().parent.parent
LIB_DIR = SKILL_DIR / "lib"
POLICY_PATH = SKILL_DIR / "policies" / "readonly.toml"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import invoke  # noqa: E402
from invoke import SafetyAssertionError, build_argv, _assert_safety  # noqa: E402


try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# build_argv invariants
# ---------------------------------------------------------------------------

def test_build_argv_contains_approval_mode_plan() -> None:
    argv = build_argv(model="gemini-3-pro-preview", prompt="hi")
    assert "--approval-mode" in argv
    idx = argv.index("--approval-mode")
    assert argv[idx + 1] == "plan"


def test_build_argv_contains_stream_json_output() -> None:
    argv = build_argv(model="gemini-3-pro-preview", prompt="hi")
    assert "-o" in argv
    idx = argv.index("-o")
    assert argv[idx + 1] == "stream-json"


def test_build_argv_contains_policy_pointing_at_existing_file() -> None:
    argv = build_argv(model="gemini-3-pro-preview", prompt="hi")
    assert "--policy" in argv
    idx = argv.index("--policy")
    policy_arg = Path(argv[idx + 1])
    assert policy_arg.exists(), f"policy file missing: {policy_arg}"
    assert policy_arg == POLICY_PATH


def test_build_argv_rejects_empty_model() -> None:
    with pytest.raises(SafetyAssertionError):
        build_argv(model="", prompt="x")


def test_build_argv_rejects_none_prompt() -> None:
    with pytest.raises(SafetyAssertionError):
        build_argv(model="m", prompt=None)  # type: ignore[arg-type]


def test_build_argv_rejects_non_string_model() -> None:
    with pytest.raises(SafetyAssertionError):
        build_argv(model=None, prompt="x")  # type: ignore[arg-type]


def test_build_argv_include_dir_appended() -> None:
    argv = build_argv(
        model="gemini-3-pro-preview",
        prompt="hi",
        include_dir=Path("/tmp/project"),
    )
    assert "--include-directories" in argv
    idx = argv.index("--include-directories")
    assert argv[idx + 1] == "/tmp/project"


# ---------------------------------------------------------------------------
# Policy TOML content
# ---------------------------------------------------------------------------

def test_policy_file_exists_and_parses_as_toml() -> None:
    assert POLICY_PATH.exists(), f"policy file missing: {POLICY_PATH}"
    with POLICY_PATH.open("rb") as fh:
        data = tomllib.load(fh)
    assert "rule" in data
    assert isinstance(data["rule"], list)
    assert len(data["rule"]) >= 3


def test_policy_denies_run_shell_command() -> None:
    with POLICY_PATH.open("rb") as fh:
        data = tomllib.load(fh)
    deny_tool_lists = [
        r.get("toolName", [])
        for r in data["rule"]
        if r.get("decision") == "deny"
    ]
    flat = [t for tl in deny_tool_lists if isinstance(tl, list) for t in tl]
    assert "run_shell_command" in flat
    assert "write_file" in flat
    assert "edit" in flat


def test_policy_denies_mcp_wildcard() -> None:
    with POLICY_PATH.open("rb") as fh:
        data = tomllib.load(fh)
    mcp_denies = [
        r for r in data["rule"]
        if r.get("mcpName") == "*" and r.get("decision") == "deny"
    ]
    assert len(mcp_denies) == 1, "expected exactly one mcp wildcard deny rule"


def test_policy_allow_rule_includes_readonly_tools() -> None:
    with POLICY_PATH.open("rb") as fh:
        data = tomllib.load(fh)
    allow_tool_lists = [
        r.get("toolName", [])
        for r in data["rule"]
        if r.get("decision") == "allow"
    ]
    flat = [t for tl in allow_tool_lists if isinstance(tl, list) for t in tl]
    for expected in (
        "read_file",
        "read_many_files",
        "glob",
        "grep",
        "list_directory",
        "google_web_search",
        "web_fetch",
    ):
        assert expected in flat, f"allow rule missing {expected}"


# ---------------------------------------------------------------------------
# _assert_safety rejects forbidden flags
# ---------------------------------------------------------------------------

BASE_SAFE_ARGV = [
    "gemini",
    "--approval-mode", "plan",
    "-m", "gemini-3-pro-preview",
    "-o", "stream-json",
    "--policy", str(POLICY_PATH),
    "-p", "hi",
]


@pytest.mark.parametrize(
    "bad_flag",
    [
        "-s",
        "--sandbox",
        "--yolo",
        "--approval-mode=auto",
        "--approval-mode=auto_edit",
        "--approval-mode=yolo",
        "--approval-mode=default",
        "--admin-policy",
        "--allowed-tools",
    ],
)
def test_assert_safety_rejects_forbidden_flag(bad_flag: str) -> None:
    argv = list(BASE_SAFE_ARGV) + [bad_flag]
    with pytest.raises(SafetyAssertionError) as exc:
        _assert_safety(argv)
    assert "forbidden" in str(exc.value).lower()


def test_assert_safety_rejects_missing_approval_mode() -> None:
    argv = [
        "gemini",
        "-m", "m",
        "-o", "stream-json",
        "--policy", str(POLICY_PATH),
        "-p", "hi",
    ]
    with pytest.raises(SafetyAssertionError):
        _assert_safety(argv)


def test_assert_safety_rejects_wrong_approval_mode_value() -> None:
    argv = [
        "gemini",
        "--approval-mode", "yolo",
        "-m", "m",
        "-o", "stream-json",
        "--policy", str(POLICY_PATH),
        "-p", "hi",
    ]
    with pytest.raises(SafetyAssertionError):
        _assert_safety(argv)


def test_assert_safety_rejects_missing_policy() -> None:
    argv = [
        "gemini",
        "--approval-mode", "plan",
        "-m", "m",
        "-o", "stream-json",
        "-p", "hi",
    ]
    with pytest.raises(SafetyAssertionError):
        _assert_safety(argv)


def test_assert_safety_rejects_non_stream_json_output() -> None:
    argv = [
        "gemini",
        "--approval-mode", "plan",
        "-m", "m",
        "-o", "json",
        "--policy", str(POLICY_PATH),
        "-p", "hi",
    ]
    with pytest.raises(SafetyAssertionError):
        _assert_safety(argv)


def test_assert_safety_accepts_clean_argv() -> None:
    # Should not raise.
    _assert_safety(list(BASE_SAFE_ARGV))


# ---------------------------------------------------------------------------
# Paths resolve relative to skill dir (no hardcoded project names)
# ---------------------------------------------------------------------------

def test_policy_path_helper_matches_expected_location() -> None:
    assert invoke.policy_path() == POLICY_PATH
