"""Regression tests for envelope quality warnings (P1-5).

Pins two observable contracts added after pilot v1:

1. `invoke.ParsedOutput.thought_events_dropped` counts `THOUGHT_EVENT_TYPES`
   events the parser drops before content aggregation. The q082 incident
   showed gemini-3-pro-preview emits CoT; operators need visibility when the
   filter kicked in even though the leak was prevented.

2. `bin/ask-gemini._quality_warnings(mode, chain)` emits:
     * `model_emitted_thought_events` whenever (1) is non-zero.
     * `zero_url_response` in research mode when the response body contains
       no http(s) URL — pilot v1 saw 10/14 ok envelopes violate the
       citation contract silently.
"""
from __future__ import annotations

import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from lib import fallback
from lib import invoke as inv


SKILL_DIR = Path(__file__).resolve().parent.parent
BIN_PATH = SKILL_DIR / "bin" / "ask-gemini"


def _jsonl(*events: dict) -> list[str]:
    return [json.dumps(e) for e in events]


@pytest.fixture(scope="module")
def cli():
    loader = SourceFileLoader("ask_gemini_cli_qw", str(BIN_PATH))
    spec = importlib.util.spec_from_loader("ask_gemini_cli_qw", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _chain(response: str, *, thought_drops: int = 0) -> fallback.ChainResult:
    parsed = inv.ParsedOutput(
        response=response,
        stats={"input_tokens": 1, "output_tokens": 1,
               "cached_tokens": 0, "total_tokens": 2},
        tool_calls=[],
        thought_events_dropped=thought_drops,
    )
    return fallback.ChainResult(
        success=True,
        model_used="gemini-3-pro-preview",
        parsed=parsed,
        fallback_triggered=False,
        attempts=[],
    )


# ---------------------------------------------------------------------------
# ParsedOutput.thought_events_dropped
# ---------------------------------------------------------------------------

def test_parsed_output_counts_dropped_thought_events():
    _, parsed = inv._parse_events(
        _jsonl(
            {"type": "thought", "content": "cot 1"},
            {"type": "thinking", "content": "cot 2"},
            {"type": "reasoning", "content": "cot 3"},
            {"type": "message", "role": "assistant", "content": "the answer"},
        )
    )
    assert parsed is not None
    assert parsed.thought_events_dropped == 3


def test_parsed_output_zero_when_no_thought_events():
    _, parsed = inv._parse_events(
        _jsonl(
            {"type": "message", "role": "assistant", "content": "the answer"},
        )
    )
    assert parsed is not None
    assert parsed.thought_events_dropped == 0


# ---------------------------------------------------------------------------
# _quality_warnings — model_emitted_thought_events
# ---------------------------------------------------------------------------

def test_warning_emitted_when_thought_events_dropped(cli):
    warns = cli._quality_warnings("research", _chain("answer https://x.com/a", thought_drops=4))
    assert "model_emitted_thought_events" in warns


def test_warning_absent_when_no_thought_events(cli):
    warns = cli._quality_warnings("research", _chain("answer https://x.com/a", thought_drops=0))
    assert "model_emitted_thought_events" not in warns


# ---------------------------------------------------------------------------
# _quality_warnings — zero_url_response (research mode only)
# ---------------------------------------------------------------------------

def test_zero_url_warning_for_research_without_urls(cli):
    warns = cli._quality_warnings("research", _chain("no links here at all"))
    assert "zero_url_response" in warns


def test_zero_url_warning_suppressed_with_https_url(cli):
    warns = cli._quality_warnings("research", _chain("see https://example.com for details"))
    assert "zero_url_response" not in warns


def test_zero_url_warning_suppressed_with_http_url(cli):
    warns = cli._quality_warnings("research", _chain("see http://example.com for details"))
    assert "zero_url_response" not in warns


def test_zero_url_warning_not_emitted_outside_research(cli):
    # analyze / second-opinion / multimodal don't promise URLs.
    for mode in ("analyze", "second-opinion", "multimodal"):
        warns = cli._quality_warnings(mode, _chain("no links here"))
        assert "zero_url_response" not in warns, f"unexpected in {mode}"


# ---------------------------------------------------------------------------
# defensive: no parsed output
# ---------------------------------------------------------------------------

def test_no_warnings_when_parsed_is_none(cli):
    chain = fallback.ChainResult(
        success=True,
        model_used="gemini-3-pro-preview",
        parsed=None,
        fallback_triggered=False,
        attempts=[],
    )
    assert cli._quality_warnings("research", chain) == []
