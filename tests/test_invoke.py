"""Tests for lib/invoke.py.

Focus: _parse_events (stream-json parsing), _prepare_env, build_argv/safety,
run() with mocked subprocess.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from lib import invoke as inv  # noqa: E402


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _jsonl(*events: dict) -> list[str]:
    return [json.dumps(e) for e in events]


# ----------------------------------------------------------------------
# _parse_events
# ----------------------------------------------------------------------

def test_parse_events_empty_input_returns_empty_and_none():
    events, parsed = inv._parse_events([])
    assert events == []
    assert parsed is None


def test_parse_events_only_blank_lines_returns_empty():
    events, parsed = inv._parse_events(["", "  ", "\t"])
    assert events == []
    assert parsed is None


def test_parse_events_skips_non_json_lines():
    lines = ["this is not json", json.dumps({"response": "hi"}), "also garbage"]
    events, parsed = inv._parse_events(lines)
    assert len(events) == 1
    assert parsed is not None
    assert parsed.response == "hi"


def test_parse_events_skips_non_dict_json():
    lines = ["[1,2,3]", '"just a string"', "42", json.dumps({"response": "ok"})]
    events, parsed = inv._parse_events(lines)
    assert len(events) == 1
    assert parsed.response == "ok"


def test_parse_events_extracts_response_field():
    events, parsed = inv._parse_events(_jsonl({"response": "Final answer."}))
    assert parsed is not None
    assert parsed.response == "Final answer."
    assert parsed.tool_calls == []


def test_parse_events_extracts_text_field_when_type_response():
    events, parsed = inv._parse_events(
        _jsonl({"type": "response", "text": "body text"})
    )
    assert parsed is not None
    assert parsed.response == "body text"


def test_parse_events_extracts_text_when_type_final():
    events, parsed = inv._parse_events(
        _jsonl({"type": "final", "text": "done"})
    )
    assert parsed.response == "done"


def test_parse_events_extracts_text_when_type_message_assistant():
    events, parsed = inv._parse_events(
        _jsonl({"type": "message", "role": "assistant", "text": "msg"})
    )
    assert parsed.response == "msg"


def test_parse_events_ignores_text_when_type_message_has_no_role():
    """`type=message` without a role is ambiguous — must not be captured.

    Gemini CLI always tags message events with role=user or role=assistant.
    A role-less message is most likely a malformed or unrelated event; prefer
    safety over assumption.
    """
    events, parsed = inv._parse_events(
        _jsonl({"type": "message", "text": "ambiguous"})
    )
    assert parsed is None


def test_parse_events_filters_user_role_echo_from_response():
    """Regression: gemini emits role=user (prompt echo) then role=assistant.

    Before this fix, `_parse_events` concatenated `content` from ALL message
    events, so `response` was polluted with the full prompt text. The real
    stream looks like:
      init → message(role=user, content=<prompt echo>) → message(role=assistant, content=<answer>, delta=true) → result
    """
    events, parsed = inv._parse_events(
        _jsonl(
            {"type": "init", "model": "gemini-3-pro-preview"},
            {"type": "message", "role": "user",
             "content": "ECHOED PROMPT TEXT — do not include in response"},
            {"type": "message", "role": "assistant",
             "content": "The answer is 4.", "delta": True},
            {"type": "result", "status": "success",
             "stats": {"total_tokens": 8484, "input_tokens": 8431, "output_tokens": 7}},
        )
    )
    assert parsed is not None
    assert parsed.response == "The answer is 4."
    assert "ECHOED PROMPT" not in parsed.response
    assert parsed.stats["total_tokens"] == 8484


def test_parse_events_drops_thought_events_q082_regression():
    """Regression for q082: `gemini-3-pro-preview` emits `type=thought` events
    whose `content` carries raw chain-of-thought ("Wait, let me search...",
    "CRITICAL INSTRUCTION...", internal tool-list enumerations).

    Before the thought-event filter, the catch-all "non-message + no role"
    fallback concatenated thought `content` into `response_text`, leaking
    5.8 KB of CoT into a 9.2 KB research answer. This test pins the fix:
    thought events must be completely dropped, assistant message must be
    the entire response, tool_calls must still be parsed from interleaved
    events.
    """
    events, parsed = inv._parse_events(
        _jsonl(
            {"type": "init", "model": "gemini-3-pro-preview"},
            {"type": "thought", "subject": "s74",
             "content": "Wait, let me search for TypeScript 5.7 release notes."},
            {"type": "tool_use", "name": "google_web_search",
             "input": {"query": "TypeScript 5.7 release"}},
            {"type": "thought", "subject": "s109",
             "content": "CRITICAL INSTRUCTION: use web_fetch on devblogs.microsoft.com."},
            {"type": "thinking",
             "content": "internal planning: 1. search 2. fetch 3. synthesize"},
            {"type": "reasoning",
             "content": "<available_tools><tool>read_file</tool></available_tools>"},
            {"type": "message", "role": "assistant",
             "content": "TypeScript 5.7 shipped in November 2024 with ..."},
            {"type": "result", "status": "success",
             "stats": {"total_tokens": 105233, "input_tokens": 102096, "output_tokens": 3137}},
        )
    )
    assert parsed is not None
    # Response must contain ONLY the assistant answer.
    assert parsed.response == "TypeScript 5.7 shipped in November 2024 with ..."
    # No CoT markers leaked.
    assert "Wait" not in parsed.response
    assert "CRITICAL INSTRUCTION" not in parsed.response
    assert "available_tools" not in parsed.response
    assert "internal planning" not in parsed.response
    # Tool calls from between thought events still parsed.
    assert parsed.tool_calls == [
        {"name": "google_web_search", "query": "TypeScript 5.7 release"}
    ]
    # Stats preserved from the result event.
    assert parsed.stats["total_tokens"] == 105233


def test_parse_events_drops_thought_even_when_only_event():
    """Isolated thought events with no assistant message produce no parse
    output (not a stringified CoT dump). Defense-in-depth: even if the
    stream is truncated after thought events, we never surface CoT.
    """
    events, parsed = inv._parse_events(
        _jsonl(
            {"type": "thought", "content": "secret CoT payload"},
            {"type": "thinking", "content": "more secret CoT"},
        )
    )
    assert parsed is None


def test_parse_events_drops_unknown_event_types_from_content_fallback():
    """A future unknown event type (e.g. `trace`, `plan`) with a `content`
    field must NOT be concatenated into response. The old blacklist-style
    `type != "message"` fallback would have included it; the new whitelist
    approach drops it.
    """
    events, parsed = inv._parse_events(
        _jsonl(
            {"type": "trace", "content": "debug trace data"},
            {"type": "message", "role": "assistant", "content": "the answer"},
        )
    )
    assert parsed is not None
    assert parsed.response == "the answer"
    assert "debug trace" not in parsed.response


def test_parse_events_accepts_role_model_as_assistant():
    """Some schemas use `role=model` instead of `role=assistant`."""
    events, parsed = inv._parse_events(
        _jsonl(
            {"type": "message", "role": "user", "content": "echo"},
            {"type": "message", "role": "model", "content": "actual answer"},
        )
    )
    assert parsed is not None
    assert parsed.response == "actual answer"


def test_parse_events_ignores_text_when_wrong_type():
    events, parsed = inv._parse_events(
        _jsonl({"type": "debug", "text": "should not be picked"})
    )
    assert parsed is None


def test_parse_events_concatenates_content_chunks():
    events, parsed = inv._parse_events(
        _jsonl(
            {"content": "Hello, "},
            {"content": "world!"},
        )
    )
    assert parsed is not None
    assert parsed.response == "Hello, world!"


def test_parse_events_concatenates_delta_chunks():
    events, parsed = inv._parse_events(
        _jsonl(
            {"delta": "foo"},
            {"delta": "bar"},
        )
    )
    assert parsed.response == "foobar"


def test_parse_events_response_wins_over_content_chunks():
    events, parsed = inv._parse_events(
        _jsonl(
            {"content": "chunk1"},
            {"response": "FINAL"},
        )
    )
    assert parsed.response == "FINAL"


def test_parse_events_tool_call_via_type_tool_use():
    events, parsed = inv._parse_events(
        _jsonl(
            {"type": "tool_use", "name": "read_file", "input": {"path": "/x.py"}},
            {"response": "done"},
        )
    )
    assert parsed is not None
    assert parsed.tool_calls == [{"name": "read_file"}]


def test_parse_events_tool_call_with_query_field():
    events, parsed = inv._parse_events(
        _jsonl(
            {"name": "google_web_search", "query": "python version"},
            {"response": "answer"},
        )
    )
    assert parsed.tool_calls == [
        {"name": "google_web_search", "query": "python version"}
    ]


def test_parse_events_tool_call_query_from_input_dict():
    events, parsed = inv._parse_events(
        _jsonl(
            {"name": "search", "input": {"query": "nested"}},
            {"response": "x"},
        )
    )
    assert parsed.tool_calls == [{"name": "search", "query": "nested"}]


def test_parse_events_tool_call_with_url():
    events, parsed = inv._parse_events(
        _jsonl(
            {"name": "web_fetch", "url": "https://ex.com", "input": "raw"},
            {"response": "x"},
        )
    )
    assert parsed.tool_calls == [{"name": "web_fetch", "url": "https://ex.com"}]


def test_parse_events_tool_call_with_path_input():
    events, parsed = inv._parse_events(
        _jsonl(
            {"name": "read_file", "path": "/tmp/f.py"},
            {"response": "x"},
        )
    )
    # path alone doesn't trigger tool recognition (needs input/query/url/path key match)
    assert parsed.tool_calls == [{"name": "read_file"}]


def test_parse_events_tool_call_fallback_name():
    events, parsed = inv._parse_events(
        _jsonl(
            {"type": "tool_use", "tool_name": "grep", "input": {}},
            {"response": "x"},
        )
    )
    assert parsed.tool_calls == [{"name": "grep"}]


def test_parse_events_tool_call_unknown_name():
    events, parsed = inv._parse_events(
        _jsonl(
            {"type": "tool_use", "input": {}},
            {"response": "x"},
        )
    )
    assert parsed.tool_calls == [{"name": "unknown"}]


def test_parse_events_stats_field():
    events, parsed = inv._parse_events(
        _jsonl(
            {"response": "hi"},
            {"stats": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}},
        )
    )
    assert parsed.stats == {
        "input_tokens": 10,
        "output_tokens": 5,
        "cached_tokens": 0,
        "total_tokens": 15,
    }


def test_parse_events_usage_field_alias():
    events, parsed = inv._parse_events(
        _jsonl(
            {"response": "hi"},
            {"usage": {"prompt_tokens": 7, "completion_tokens": 3}},
        )
    )
    assert parsed.stats["input_tokens"] == 7
    assert parsed.stats["output_tokens"] == 3
    # total derived since not provided
    assert parsed.stats["total_tokens"] == 10


def test_parse_events_stats_total_autocomputed_when_missing():
    events, parsed = inv._parse_events(
        _jsonl(
            {"response": "hi"},
            {"stats": {"input_tokens": 4, "output_tokens": 6, "cached_tokens": 2}},
        )
    )
    assert parsed.stats["total_tokens"] == 12


def test_parse_events_stats_none_values_become_zero():
    """`int(None or 0)` → 0 is the guard pattern used in invoke._parse_events."""
    events, parsed = inv._parse_events(
        _jsonl(
            {"response": "hi"},
            {"stats": {"input_tokens": None, "output_tokens": None,
                       "total_tokens": None, "cached_tokens": None}},
        )
    )
    assert parsed.stats == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "total_tokens": 0,
    }


def test_parse_events_cached_tokens_alias():
    events, parsed = inv._parse_events(
        _jsonl(
            {"response": "hi"},
            {"stats": {"cache_read_tokens": 3, "total_tokens": 10}},
        )
    )
    assert parsed.stats["cached_tokens"] == 3


def test_parse_events_no_response_returns_none():
    events, parsed = inv._parse_events(
        _jsonl({"type": "debug", "msg": "starting"})
    )
    assert len(events) == 1
    assert parsed is None


def test_parse_events_multiple_tool_calls_preserved_in_order():
    events, parsed = inv._parse_events(
        _jsonl(
            {"name": "tool_a", "query": "q1"},
            {"name": "tool_b", "query": "q2"},
            {"response": "done"},
        )
    )
    assert [c["name"] for c in parsed.tool_calls] == ["tool_a", "tool_b"]


# ----------------------------------------------------------------------
# _prepare_env
# ----------------------------------------------------------------------

def test_prepare_env_strips_gcp_by_default(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    monkeypatch.delenv("ASK_GEMINI_KEEP_GCP", raising=False)
    env = inv._prepare_env()
    assert "GOOGLE_CLOUD_PROJECT" not in env


def test_prepare_env_keeps_gcp_when_opt_in(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    monkeypatch.setenv("ASK_GEMINI_KEEP_GCP", "1")
    env = inv._prepare_env()
    assert env.get("GOOGLE_CLOUD_PROJECT") == "my-project"


def test_prepare_env_passes_through_api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    env = inv._prepare_env()
    assert env.get("GEMINI_API_KEY") == "secret-key"


def test_prepare_env_no_gcp_set_is_noop(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    env = inv._prepare_env()
    assert "GOOGLE_CLOUD_PROJECT" not in env


# ----------------------------------------------------------------------
# gemini_bin / skill_dir / policy_path
# ----------------------------------------------------------------------

def test_gemini_bin_default_when_neither_env_nor_path(monkeypatch):
    """No GEMINI_BIN, no `gemini` on $PATH → falls back to DEFAULT_GEMINI_BIN."""
    monkeypatch.delenv("GEMINI_BIN", raising=False)
    monkeypatch.setattr(inv.shutil, "which", lambda _name: None)
    # DEFAULT path is rejected by validate (it's `/opt/homebrew/...` which is
    # not in dangerous prefixes), so this should pass through.
    assert inv.gemini_bin() == inv.DEFAULT_GEMINI_BIN


def test_gemini_bin_uses_path_lookup_when_no_env(monkeypatch):
    """No GEMINI_BIN, but `gemini` on $PATH → use PATH-resolved binary.

    This is the fix for v1.1.6: Linux/Intel-Mac users with `gemini`
    installed via npm/apt/nvm at non-Homebrew paths shouldn't have to
    set GEMINI_BIN manually.
    """
    monkeypatch.delenv("GEMINI_BIN", raising=False)
    monkeypatch.setattr(
        inv.shutil, "which", lambda name: "/home/u/.nvm/versions/node/v24/bin/gemini"
    )
    assert inv.gemini_bin() == "/home/u/.nvm/versions/node/v24/bin/gemini"


def test_gemini_bin_env_overrides_path_lookup(monkeypatch):
    """Explicit GEMINI_BIN takes priority over $PATH lookup."""
    monkeypatch.setenv("GEMINI_BIN", "/custom/path/gemini")
    monkeypatch.setattr(inv.shutil, "which", lambda _name: "/usr/local/bin/gemini")
    assert inv.gemini_bin() == "/custom/path/gemini"


def test_gemini_bin_path_lookup_still_screened_for_world_writable(monkeypatch):
    """Even when shutil.which finds a binary, /tmp/* is still rejected."""
    monkeypatch.delenv("GEMINI_BIN", raising=False)
    monkeypatch.delenv("ASK_GEMINI_BIN_UNRESTRICTED", raising=False)
    monkeypatch.setattr(inv.shutil, "which", lambda _name: "/tmp/evil/gemini")
    with pytest.raises(inv.SafetyAssertionError):
        inv.gemini_bin()


def test_skill_dir_is_directory_with_policies():
    d = inv.skill_dir()
    assert d.is_dir()
    assert (d / "policies").is_dir()


def test_policy_path_points_to_readonly_toml():
    p = inv.policy_path()
    assert p.name == "readonly.toml"
    assert p.exists()


# ----------------------------------------------------------------------
# build_argv
# ----------------------------------------------------------------------

def test_build_argv_basic_shape():
    argv = inv.build_argv(model="gemini-2.5-pro", prompt="hello")
    assert argv[0] == inv.gemini_bin()
    assert "--approval-mode" in argv
    assert "plan" in argv
    assert "-m" in argv
    assert "gemini-2.5-pro" in argv
    assert "-o" in argv
    assert "stream-json" in argv
    assert "--policy" in argv
    assert "-p" in argv
    assert argv[-1] == "hello"


def test_build_argv_with_include_dir(tmp_path):
    argv = inv.build_argv(model="m", prompt="p", include_dir=tmp_path)
    assert "--include-directories" in argv
    idx = argv.index("--include-directories")
    assert argv[idx + 1] == str(tmp_path)


def test_build_argv_empty_model_raises():
    with pytest.raises(inv.SafetyAssertionError):
        inv.build_argv(model="", prompt="p")


def test_build_argv_none_prompt_raises():
    with pytest.raises(inv.SafetyAssertionError):
        inv.build_argv(model="m", prompt=None)  # type: ignore[arg-type]


def test_build_argv_non_string_model_raises():
    with pytest.raises(inv.SafetyAssertionError):
        inv.build_argv(model=123, prompt="p")  # type: ignore[arg-type]


def test_build_argv_rejects_dash_prefixed_include_dir(tmp_path):
    """H2: an include_dir whose string form starts with '-' would be parsed by
    gemini as an option flag (argv injection). Must raise before spawn.
    """
    evil = Path("-rf")
    with pytest.raises(inv.SafetyAssertionError, match="argv injection"):
        inv.build_argv(model="m", prompt="p", include_dir=evil)


def test_build_argv_allows_legitimate_hidden_dir(tmp_path):
    """Paths containing '-' after the first char are fine; only leading '-' is rejected."""
    d = tmp_path / "has-dash-inside"
    d.mkdir()
    argv = inv.build_argv(model="m", prompt="p", include_dir=d)
    assert str(d) in argv


# ----------------------------------------------------------------------
# _assert_safety (direct tests of remaining branches)
# ----------------------------------------------------------------------

def test_assert_safety_missing_policy():
    argv = [
        "gemini",
        "--approval-mode", "plan",
        "-m", "x",
        "-o", "stream-json",
        "-p", "hi",
    ]
    with pytest.raises(inv.SafetyAssertionError, match="policy"):
        inv._assert_safety(argv)


def test_assert_safety_approval_mode_missing_arg():
    argv = ["gemini", "--approval-mode"]
    with pytest.raises(inv.SafetyAssertionError):
        inv._assert_safety(argv)


def test_assert_safety_output_missing_arg():
    argv = [
        "gemini",
        "--approval-mode", "plan",
        "-o",
    ]
    with pytest.raises(inv.SafetyAssertionError):
        inv._assert_safety(argv)


# ----------------------------------------------------------------------
# run() — mocked subprocess
# ----------------------------------------------------------------------

def _make_completed(returncode: int, stdout: str = "", stderr: str = ""):
    cp = mock.MagicMock(spec=subprocess.CompletedProcess)
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


def test_run_success_parses_response(monkeypatch):
    stdout = json.dumps({"response": "ok!", "stats": {"total_tokens": 5}}) + "\n"
    fake = _make_completed(0, stdout=stdout, stderr="")
    monkeypatch.setattr(inv.subprocess, "run", lambda *a, **kw: fake)

    result = inv.run(model="gemini-2.5-pro", prompt="hi", timeout_s=10)
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.parsed is not None
    assert result.parsed.response == "ok!"
    assert result.stderr == ""
    assert result.duration_ms >= 0


def test_run_nonzero_exit_with_stderr(monkeypatch):
    fake = _make_completed(1, stdout="", stderr="quota exceeded")
    monkeypatch.setattr(inv.subprocess, "run", lambda *a, **kw: fake)

    result = inv.run(model="m", prompt="p", timeout_s=5)
    assert result.exit_code == 1
    assert result.stderr == "quota exceeded"
    assert result.parsed is None


def test_run_handles_timeout_with_string_output(monkeypatch):
    exc = subprocess.TimeoutExpired(cmd="gemini", timeout=1)
    exc.stdout = "partial"
    exc.stderr = "err"

    def fake_run(*a, **kw):
        raise exc

    monkeypatch.setattr(inv.subprocess, "run", fake_run)
    result = inv.run(model="m", prompt="p", timeout_s=1)
    assert result.timed_out is True
    assert result.exit_code == -1
    assert result.stderr == "err"


def test_run_handles_timeout_with_bytes_output(monkeypatch):
    exc = subprocess.TimeoutExpired(cmd="gemini", timeout=1)
    exc.stdout = b"partial-bytes"
    exc.stderr = b"stderr-bytes"

    def fake_run(*a, **kw):
        raise exc

    monkeypatch.setattr(inv.subprocess, "run", fake_run)
    result = inv.run(model="m", prompt="p", timeout_s=1)
    assert result.timed_out is True
    assert result.stderr == "stderr-bytes"


def test_run_handles_timeout_with_none_output(monkeypatch):
    exc = subprocess.TimeoutExpired(cmd="gemini", timeout=1)
    exc.stdout = None
    exc.stderr = None

    def fake_run(*a, **kw):
        raise exc

    monkeypatch.setattr(inv.subprocess, "run", fake_run)
    result = inv.run(model="m", prompt="p", timeout_s=1)
    assert result.timed_out is True
    assert result.stderr == ""
    assert result.raw_events == []


def test_run_with_include_dir(monkeypatch, tmp_path):
    captured_argv: list[list[str]] = []

    def fake_run(argv, **kw):
        captured_argv.append(argv)
        return _make_completed(0, stdout="", stderr="")

    monkeypatch.setattr(inv.subprocess, "run", fake_run)
    inv.run(model="m", prompt="p", timeout_s=1, include_dir=tmp_path)

    assert captured_argv
    argv = captured_argv[0]
    assert "--include-directories" in argv
    idx = argv.index("--include-directories")
    assert argv[idx + 1] == str(tmp_path)
