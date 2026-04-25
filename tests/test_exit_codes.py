"""Unit tests for lib.exit_codes.classify()."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the skill dir importable as a root so `from lib...` resolves.
_SKILL_DIR = Path(__file__).resolve().parent.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

import pytest  # noqa: E402

from lib.exit_codes import (  # noqa: E402
    classify,
    KIND_AUTH,
    KIND_BAD_INPUT,
    KIND_CONFIG,
    KIND_GENERAL,
    KIND_MALFORMED_OUTPUT,
    KIND_TIMEOUT,
    KIND_TRANSIENT,
    KIND_TURN_LIMIT,
)


# ---------------------------------------------------------------------------
# exit 0 branches
# ---------------------------------------------------------------------------


def test_exit_zero_parsed_ok_no_fallback() -> None:
    c = classify(exit_code=0, stderr="", parsed_ok=True)
    assert c.kind == KIND_GENERAL
    assert c.should_fallback is False
    assert c.setup_hint  # non-empty actionable text


def test_exit_zero_unparseable_is_malformed_output() -> None:
    c = classify(exit_code=0, stderr="", parsed_ok=False)
    assert c.kind == KIND_MALFORMED_OUTPUT
    assert c.should_fallback is False
    assert "stream-json" in c.setup_hint or "unparseable" in c.setup_hint.lower()


# ---------------------------------------------------------------------------
# documented non-zero exit codes
# ---------------------------------------------------------------------------


def test_exit_41_is_auth_no_fallback() -> None:
    c = classify(exit_code=41, stderr="auth failed")
    assert c.kind == KIND_AUTH
    assert c.should_fallback is False
    assert "GEMINI_API_KEY" in c.setup_hint


def test_exit_42_is_bad_input_no_fallback() -> None:
    c = classify(exit_code=42, stderr="invalid flag")
    assert c.kind == KIND_BAD_INPUT
    assert c.should_fallback is False


def test_exit_44_is_config_no_fallback() -> None:
    c = classify(exit_code=44, stderr="sandbox error")
    assert c.kind == KIND_CONFIG
    assert c.should_fallback is False


def test_exit_52_is_config_no_fallback() -> None:
    c = classify(exit_code=52, stderr="bad config")
    assert c.kind == KIND_CONFIG
    assert c.should_fallback is False


def test_exit_53_is_turn_limit_no_fallback() -> None:
    c = classify(exit_code=53, stderr="turn limit reached")
    assert c.kind == KIND_TURN_LIMIT
    assert c.should_fallback is False


# ---------------------------------------------------------------------------
# exit 1 + stderr pattern matching (transient)
# ---------------------------------------------------------------------------


def test_exit_1_resource_exhausted_is_transient_fallback() -> None:
    c = classify(exit_code=1, stderr="RESOURCE_EXHAUSTED: quota exceeded for project")
    assert c.kind == KIND_TRANSIENT
    assert c.should_fallback is True


def test_exit_1_http_429_is_transient_fallback() -> None:
    c = classify(exit_code=1, stderr="Error: HTTP 429 rate limit hit")
    assert c.kind == KIND_TRANSIENT
    assert c.should_fallback is True


def test_exit_1_http_503_unavailable_is_transient_fallback() -> None:
    c = classify(exit_code=1, stderr="upstream returned HTTP 503 UNAVAILABLE")
    assert c.kind == KIND_TRANSIENT
    assert c.should_fallback is True


def test_exit_1_deadline_exceeded_is_transient_fallback() -> None:
    c = classify(exit_code=1, stderr="DEADLINE_EXCEEDED after 60s")
    assert c.kind == KIND_TRANSIENT
    assert c.should_fallback is True


# ---------------------------------------------------------------------------
# exit 1 other + misc
# ---------------------------------------------------------------------------


def test_exit_1_unknown_stderr_is_general_no_fallback() -> None:
    c = classify(exit_code=1, stderr="syntax error in prompt")
    assert c.kind == KIND_GENERAL
    assert c.should_fallback is False


def test_timed_out_flag_is_timeout_fallback() -> None:
    # Subprocess timeout returns exit_code -1 and timed_out=True.
    c = classify(exit_code=-1, stderr="", timed_out=True)
    assert c.kind == KIND_TIMEOUT
    assert c.should_fallback is True


def test_timed_out_takes_precedence_over_stderr_text() -> None:
    # Even if stderr happens to contain a transient marker, timed_out wins.
    c = classify(exit_code=-1, stderr="HTTP 503", timed_out=True)
    assert c.kind == KIND_TIMEOUT
    assert c.should_fallback is True


def test_unknown_exit_code_is_general_no_fallback() -> None:
    c = classify(exit_code=17, stderr="something weird")
    assert c.kind == KIND_GENERAL
    assert c.should_fallback is False


@pytest.mark.parametrize(
    "stderr",
    [
        "quota exceeded",
        "Quota Exceeded",
        "rate-limit enforced",
        "rate limit triggered",
    ],
)
def test_exit_1_quota_variants_match(stderr: str) -> None:
    c = classify(exit_code=1, stderr=stderr)
    assert c.kind == KIND_TRANSIENT
    assert c.should_fallback is True
