"""Unit tests for evals.lib.heuristics."""

from __future__ import annotations

import sys
from pathlib import Path

EVALS_ROOT = Path(__file__).resolve().parent.parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from lib.heuristics import (  # noqa: E402
    compute_heuristics,
    count_google_search_calls,
    extract_urls,
    is_refusal,
    is_short_response,
)


# ---------- extract_urls ----------


def test_extract_urls_finds_multiple():
    text = "see https://a.com/x and http://b.example.org/page?q=1 also https://c.dev."
    urls = extract_urls(text)
    assert urls == ["https://a.com/x", "http://b.example.org/page?q=1", "https://c.dev"]


def test_extract_urls_ignores_trailing_punct():
    assert extract_urls("visit https://a.com.") == ["https://a.com"]
    assert extract_urls("(https://b.com)") == ["https://b.com"]


def test_extract_urls_empty_and_none():
    assert extract_urls(None) == []
    assert extract_urls("") == []
    assert extract_urls("no links here") == []


# ---------- is_refusal ----------


def test_is_refusal_matches_common_phrases():
    assert is_refusal("Sorry, I don't know the answer.") is True
    assert is_refusal("I could not find any results on this topic.") is True
    assert is_refusal("我不知道这个问题的答案") is True


def test_is_refusal_false_on_confident_answer():
    assert is_refusal("The answer is 42. See https://x.com for details.") is False
    assert is_refusal("") is False
    assert is_refusal(None) is False


# ---------- is_short_response ----------


def test_is_short_response():
    assert is_short_response("hi") is True
    assert is_short_response("a" * 50) is True
    assert is_short_response("a" * 200) is False
    assert is_short_response(None) is True
    assert is_short_response("   ") is True  # whitespace only


# ---------- count_google_search_calls ----------


def test_count_google_search_calls():
    calls = [
        {"name": "google_web_search", "args": {}},
        {"name": "read_file"},
        {"name": "google_web_search"},
    ]
    assert count_google_search_calls(calls) == 2
    assert count_google_search_calls([]) == 0
    assert count_google_search_calls(None) == 0


# ---------- compute_heuristics ----------


def _base_envelope(**overrides) -> dict:
    env = {
        "ok": True,
        "mode": "research",
        "model_used": "gemini-3-pro-preview",
        "fallback_triggered": False,
        "attempts": [{"model": "gemini-3-pro-preview"}],
        "response": (
            "The answer is here with enough prose to clear the short-response "
            "threshold comfortably. See https://example.com for details, and "
            "note that this fixture mirrors a real research response length."
        ),
        "stats": {"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500},
        "tool_calls": [{"name": "google_web_search"}, {"name": "google_web_search"}],
        "error": None,
        "_runner": {"id": "q001", "wall_ms": 12345},
    }
    env.update(overrides)
    return env


def test_compute_heuristics_happy_path():
    meta = {"id": "q001", "time_sensitivity": "strong", "domain": "tech", "difficulty": 1}
    h = compute_heuristics(_base_envelope(), query_meta=meta)
    assert h.id == "q001"
    assert h.ok is True
    assert h.model_used == "gemini-3-pro-preview"
    assert h.fallback_triggered is False
    assert h.url_count == 1
    assert h.has_url is True
    assert h.refusal_hit is False
    assert h.short_response is False
    assert h.google_search_calls == 2
    assert h.total_tool_calls == 2
    assert h.attempts_count == 1
    assert h.wall_ms == 12345
    assert h.total_tokens == 1500
    assert h.time_sensitivity == "strong"
    assert h.domain == "tech"
    assert h.difficulty == 1


def test_compute_heuristics_error_envelope():
    env = _base_envelope(
        ok=False, response=None, stats=None, tool_calls=[],
        attempts=[], model_used=None,
        error={"category": "timeout", "message": "x"},
    )
    h = compute_heuristics(env, query_meta={"id": "q001"})
    assert h.ok is False
    assert h.error_category == "timeout"
    assert h.response_len == 0
    assert h.url_count == 0
    assert h.has_url is False
    assert h.short_response is True
    assert h.google_search_calls == 0
    assert h.total_tokens == 0


def test_compute_heuristics_refusal_response():
    env = _base_envelope(response="I could not find any reliable information on this.")
    h = compute_heuristics(env, query_meta={"id": "q001"})
    assert h.refusal_hit is True
    assert h.url_count == 0


def test_compute_heuristics_short_response_flag():
    env = _base_envelope(response="ok.")
    h = compute_heuristics(env, query_meta={"id": "q001"})
    assert h.short_response is True
    assert h.response_len == 3


def test_compute_heuristics_missing_runner_block():
    env = _base_envelope()
    env.pop("_runner")
    h = compute_heuristics(env, query_meta={"id": "qfoo"})
    assert h.id == "qfoo"
    assert h.wall_ms == 0
