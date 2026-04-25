"""Unit tests for lib.fallback.run_with_fallback().

Tests inject a FakeRunner so no real gemini subprocess is ever spawned.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Make the skill dir importable as a root.
_SKILL_DIR = Path(__file__).resolve().parent.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from lib import invoke as invoke_mod  # noqa: E402
from lib.fallback import (  # noqa: E402
    FALLBACK_CHAIN,
    TIMEOUTS_S,
    run_with_fallback,
)
from lib.exit_codes import (  # noqa: E402
    KIND_AUTH,
    KIND_MALFORMED_OUTPUT,
    KIND_QUOTA_EXHAUSTED,
)


# ---------------------------------------------------------------------------
# Fake runner helpers
# ---------------------------------------------------------------------------


@dataclass
class _CallRecord:
    model: str
    prompt: str
    include_dir: Optional[Path]
    timeout_s: int


def _ok_result(duration_ms: int = 100) -> invoke_mod.InvokeResult:
    parsed = invoke_mod.ParsedOutput(
        response="hello",
        stats={"input_tokens": 1, "output_tokens": 1, "cached_tokens": 0, "total_tokens": 2},
        tool_calls=[],
    )
    return invoke_mod.InvokeResult(
        exit_code=0,
        duration_ms=duration_ms,
        stderr="",
        raw_events=[],
        parsed=parsed,
        timed_out=False,
    )


def _quota_result(duration_ms: int = 50) -> invoke_mod.InvokeResult:
    return invoke_mod.InvokeResult(
        exit_code=1,
        duration_ms=duration_ms,
        stderr="RESOURCE_EXHAUSTED: quota exceeded on model",
        raw_events=[],
        parsed=None,
        timed_out=False,
    )


def _auth_result(duration_ms: int = 10) -> invoke_mod.InvokeResult:
    return invoke_mod.InvokeResult(
        exit_code=41,
        duration_ms=duration_ms,
        stderr="auth failure: missing API key",
        raw_events=[],
        parsed=None,
        timed_out=False,
    )


def _malformed_result(duration_ms: int = 75) -> invoke_mod.InvokeResult:
    # Clean exit but no parseable final response.
    return invoke_mod.InvokeResult(
        exit_code=0,
        duration_ms=duration_ms,
        stderr="",
        raw_events=[{"type": "noise"}],
        parsed=None,
        timed_out=False,
    )


class FakeRunner:
    """Scripted runner — pops one result per call; records invocations."""

    def __init__(self, results: list[invoke_mod.InvokeResult]):
        self._queue = list(results)
        self.calls: list[_CallRecord] = []

    def __call__(
        self,
        *,
        model: str,
        prompt: str,
        timeout_s: int,
        include_dir: Optional[Path] = None,
    ) -> invoke_mod.InvokeResult:
        self.calls.append(
            _CallRecord(
                model=model,
                prompt=prompt,
                include_dir=include_dir,
                timeout_s=timeout_s,
            )
        )
        if not self._queue:
            raise AssertionError(f"FakeRunner exhausted; unexpected call for model={model}")
        return self._queue.pop(0)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def test_first_model_succeeds_single_attempt() -> None:
    runner = FakeRunner([_ok_result()])
    result = run_with_fallback(prompt="hi", runner=runner)

    assert result.success is True
    assert result.model_used == FALLBACK_CHAIN[0]
    assert result.fallback_triggered is False
    assert len(result.attempts) == 1
    assert result.attempts[0].model == FALLBACK_CHAIN[0]
    assert result.attempts[0].exit_code == 0
    assert result.parsed is not None
    assert result.parsed.response == "hello"
    assert result.final_kind is None
    # timeout was passed through from the TIMEOUTS_S table
    assert runner.calls[0].timeout_s == TIMEOUTS_S[FALLBACK_CHAIN[0]]


def test_first_quota_then_second_succeeds_triggers_fallback() -> None:
    runner = FakeRunner([_quota_result(), _ok_result()])
    result = run_with_fallback(prompt="hi", runner=runner)

    assert result.success is True
    assert result.model_used == FALLBACK_CHAIN[1]
    assert result.fallback_triggered is True
    assert len(result.attempts) == 2
    assert [a.model for a in result.attempts] == FALLBACK_CHAIN[:2]
    assert result.attempts[0].exit_code == 1
    assert result.attempts[1].exit_code == 0


def test_two_quota_then_flash_succeeds() -> None:
    runner = FakeRunner([_quota_result(), _quota_result(), _ok_result()])
    result = run_with_fallback(prompt="hi", runner=runner)

    assert result.success is True
    assert result.model_used == FALLBACK_CHAIN[2]  # gemini-2.5-flash
    assert result.fallback_triggered is True
    assert len(result.attempts) == 3
    assert [a.model for a in result.attempts] == FALLBACK_CHAIN


def test_all_three_quota_exhausted_returns_quota_exhausted() -> None:
    runner = FakeRunner([_quota_result(), _quota_result(), _quota_result()])
    result = run_with_fallback(prompt="hi", runner=runner)

    assert result.success is False
    assert result.model_used is None
    assert result.fallback_triggered is True
    assert len(result.attempts) == 3
    assert result.final_kind == KIND_QUOTA_EXHAUSTED
    assert result.final_exit_code == 1
    assert "quota" in result.final_stderr_tail.lower()
    assert result.final_setup_hint  # actionable hint present


def test_auth_failure_on_first_model_no_fallback() -> None:
    runner = FakeRunner([_auth_result()])
    result = run_with_fallback(prompt="hi", runner=runner)

    assert result.success is False
    assert result.model_used is None
    assert result.fallback_triggered is False
    assert len(result.attempts) == 1
    assert result.final_kind == KIND_AUTH
    assert result.final_exit_code == 41
    assert "GEMINI_API_KEY" in result.final_setup_hint


def test_malformed_output_on_first_model_no_fallback() -> None:
    runner = FakeRunner([_malformed_result()])
    result = run_with_fallback(prompt="hi", runner=runner)

    assert result.success is False
    assert result.model_used is None
    assert result.fallback_triggered is False
    assert len(result.attempts) == 1
    assert result.final_kind == KIND_MALFORMED_OUTPUT
    # exit code was 0, but overall success is False because parsed is None.
    assert result.final_exit_code == 0
    assert result.parsed is None
