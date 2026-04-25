"""Unit tests for lib.envelope (build_success / build_error / tail_lines)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from lib import envelope  # noqa: E402
from lib.fallback import Attempt, ChainResult  # noqa: E402
from lib.invoke import ParsedOutput  # noqa: E402


def _make_parsed(response: str = "hi", stats: dict | None = None,
                 tool_calls: list[dict] | None = None) -> ParsedOutput:
    return ParsedOutput(
        response=response,
        stats=stats if stats is not None else {},
        tool_calls=tool_calls if tool_calls is not None else [],
    )


def _minimal_chain() -> ChainResult:
    parsed = _make_parsed(
        response="hello world",
        stats={"input_tokens": 100, "output_tokens": 20,
               "cached_tokens": 0, "total_tokens": 120},
    )
    return ChainResult(
        success=True,
        model_used="gemini-3-pro-preview",
        fallback_triggered=False,
        attempts=[Attempt(model="gemini-3-pro-preview", exit_code=0, duration_ms=1000)],
        parsed=parsed,
    )


# --------------------------------------------------------------------------- #
# build_success
# --------------------------------------------------------------------------- #

def test_build_success_minimal_shape() -> None:
    env = envelope.build_success(
        mode="analyze",
        chain_result=_minimal_chain(),
        persisted_to=None,
        warnings=None,
    )
    assert env["ok"] is True
    assert env["mode"] == "analyze"
    assert env["model_used"] == "gemini-3-pro-preview"
    assert env["fallback_triggered"] is False
    assert env["tool_calls"] == []
    assert env["warnings"] == []
    assert env["stats"] == {
        "input_tokens": 100, "output_tokens": 20,
        "cached_tokens": 0, "total_tokens": 120,
    }
    assert env["persisted_to"] is None
    assert env["response"] == "hello world"


def test_build_success_with_three_attempts_sets_fallback_triggered() -> None:
    chain = _minimal_chain()
    chain.fallback_triggered = True
    chain.model_used = "gemini-2.5-flash"
    chain.attempts = [
        Attempt(model="gemini-3-pro-preview", exit_code=1, duration_ms=500),
        Attempt(model="gemini-2.5-pro", exit_code=1, duration_ms=600),
        Attempt(model="gemini-2.5-flash", exit_code=0, duration_ms=700),
    ]
    env = envelope.build_success(mode="research", chain_result=chain)
    assert env["fallback_triggered"] is True
    assert len(env["attempts"]) == 3
    assert env["attempts"][0]["model"] == "gemini-3-pro-preview"
    assert env["attempts"][-1]["exit_code"] == 0


def test_build_success_persisted_to_none_stays_none() -> None:
    env = envelope.build_success(
        mode="analyze", chain_result=_minimal_chain(), persisted_to=None,
    )
    assert "persisted_to" in env
    assert env["persisted_to"] is None


def test_build_success_persisted_to_string() -> None:
    env = envelope.build_success(
        mode="analyze", chain_result=_minimal_chain(),
        persisted_to="/tmp/x.md",
    )
    assert env["persisted_to"] == "/tmp/x.md"
    assert isinstance(env["persisted_to"], str)


def test_build_success_warnings_passed_through() -> None:
    env = envelope.build_success(
        mode="analyze", chain_result=_minimal_chain(),
        warnings=["target dir auto-trusted for first use"],
    )
    assert env["warnings"] == ["target dir auto-trusted for first use"]


def test_build_success_tool_calls_preserved() -> None:
    chain = _minimal_chain()
    chain.parsed = _make_parsed(
        response="r",
        stats={},
        tool_calls=[{"name": "google_web_search", "query": "node lts"}],
    )
    env = envelope.build_success(mode="research", chain_result=chain)
    assert env["tool_calls"] == [{"name": "google_web_search", "query": "node lts"}]


def test_build_success_missing_parsed_has_empty_defaults() -> None:
    chain = ChainResult(
        success=True, model_used="gemini-2.5-flash",
        fallback_triggered=False, attempts=[], parsed=None,
    )
    env = envelope.build_success(mode="analyze", chain_result=chain)
    assert env["response"] == ""
    assert env["tool_calls"] == []
    assert env["stats"] == {
        "input_tokens": 0, "output_tokens": 0,
        "cached_tokens": 0, "total_tokens": 0,
    }


# --------------------------------------------------------------------------- #
# build_error
# --------------------------------------------------------------------------- #

def test_build_error_minimal() -> None:
    env = envelope.build_error(
        mode="analyze", kind="auth", message="not authenticated",
        setup_hint="Set GEMINI_API_KEY",
    )
    assert env["ok"] is False
    assert env["mode"] == "analyze"
    assert env["attempts"] == []
    assert env["error"]["kind"] == "auth"
    assert env["error"]["message"] == "not authenticated"
    assert env["error"]["setup_hint"] == "Set GEMINI_API_KEY"
    assert env["error"]["exit_code"] == 0
    assert env["error"]["stderr_tail"] == ""


def test_build_error_with_attempts() -> None:
    env = envelope.build_error(
        mode="research", kind="quota_exhausted",
        message="chain exhausted", setup_hint="wait",
        exit_code=1, stderr_tail="429 RESOURCE_EXHAUSTED",
        attempts=[Attempt(model="gemini-3-pro-preview", exit_code=1, duration_ms=42)],
    )
    assert env["ok"] is False
    assert len(env["attempts"]) == 1
    assert env["attempts"][0] == {
        "model": "gemini-3-pro-preview",
        "exit_code": 1,
        "duration_ms": 42,
    }
    assert env["error"]["exit_code"] == 1
    assert env["error"]["stderr_tail"] == "429 RESOURCE_EXHAUSTED"


# --------------------------------------------------------------------------- #
# tail_lines
# --------------------------------------------------------------------------- #

def test_tail_lines_basic() -> None:
    assert envelope.tail_lines("a\nb\nc\n", n=2) == "b\nc"


def test_tail_lines_empty_string() -> None:
    assert envelope.tail_lines("", n=10) == ""


def test_tail_lines_fewer_lines_than_requested() -> None:
    assert envelope.tail_lines("only\n", n=5) == "only"


# --------------------------------------------------------------------------- #
# JSON round-trip
# --------------------------------------------------------------------------- #

def test_envelopes_round_trip_through_json() -> None:
    success = envelope.build_success(mode="analyze", chain_result=_minimal_chain())
    error = envelope.build_error(
        mode="analyze", kind="bad_input", message="oops", setup_hint="fix it",
    )
    for env in (success, error):
        text = json.dumps(env, ensure_ascii=False)
        parsed = json.loads(text)
        assert parsed == env


# --------------------------------------------------------------------------- #
# Edge cases — defensive coercion
# --------------------------------------------------------------------------- #

def test_attempt_to_dict_handles_none() -> None:
    assert envelope._attempt_to_dict(None) == {
        "model": "", "exit_code": 0, "duration_ms": 0
    }


def test_attempt_to_dict_handles_plain_dict() -> None:
    d = envelope._attempt_to_dict(
        {"model": "gx", "exit_code": 2, "duration_ms": 55}
    )
    assert d == {"model": "gx", "exit_code": 2, "duration_ms": 55}


def test_attempt_to_dict_handles_object_with_attrs() -> None:
    class Fake:
        model = "gm"
        exit_code = 7
        duration_ms = 99
    d = envelope._attempt_to_dict(Fake())
    assert d == {"model": "gm", "exit_code": 7, "duration_ms": 99}


def test_attempt_to_dict_coerces_nonnumeric_exit_code() -> None:
    d = envelope._attempt_to_dict(
        {"model": 123, "exit_code": None, "duration_ms": None}
    )
    assert d["model"] == "123"
    assert d["exit_code"] == 0
    assert d["duration_ms"] == 0


def test_normalize_stats_handles_non_dict() -> None:
    out = envelope._normalize_stats("not a dict")
    assert out == {
        "input_tokens": 0, "output_tokens": 0,
        "cached_tokens": 0, "total_tokens": 0,
    }


def test_normalize_stats_bad_int_becomes_zero() -> None:
    out = envelope._normalize_stats(
        {"input_tokens": "bad", "output_tokens": 5,
         "cached_tokens": None, "total_tokens": None}
    )
    assert out["input_tokens"] == 0
    assert out["output_tokens"] == 5
    assert out["cached_tokens"] == 0
    assert out["total_tokens"] == 0


def test_normalize_tool_calls_handles_non_list() -> None:
    assert envelope._normalize_tool_calls("not a list") == []


def test_normalize_tool_calls_skips_non_dicts() -> None:
    out = envelope._normalize_tool_calls(
        [{"name": "a"}, "string-entry", 42, None, {"name": "b"}]
    )
    assert out == [{"name": "a"}, {"name": "b"}]


def test_build_error_with_bad_exit_code_coerces_to_zero() -> None:
    env = envelope.build_error(
        mode="x", kind="general", message="m",
        exit_code="not-a-number",  # type: ignore[arg-type]
    )
    assert env["error"]["exit_code"] == 0


def test_build_error_attempts_non_list_becomes_empty() -> None:
    env = envelope.build_error(
        mode="x", kind="general", message="m",
        attempts="not a list",  # type: ignore[arg-type]
    )
    assert env["attempts"] == []


def test_tail_lines_zero_returns_empty() -> None:
    assert envelope.tail_lines("a\nb\nc", n=0) == ""


def test_tail_lines_negative_returns_empty() -> None:
    assert envelope.tail_lines("a\nb\nc", n=-3) == ""
