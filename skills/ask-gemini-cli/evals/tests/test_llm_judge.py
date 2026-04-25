"""Unit tests for evals.lib.llm_judge — all Anthropic calls mocked."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

EVALS_ROOT = Path(__file__).resolve().parent.parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from lib import llm_judge  # noqa: E402


def test_build_user_message_includes_query_and_answer():
    msg = llm_judge.build_user_message("what is X?", "X is 42. See https://a.com.")
    assert "<user_query>" in msg
    assert "what is X?" in msg
    assert "<assistant_answer>" in msg
    assert "https://a.com" in msg


def test_build_user_message_handles_empty_response():
    msg = llm_judge.build_user_message("q", "")
    assert "(empty response)" in msg


def test_build_messages_kwargs_marks_rubric_cacheable():
    kw = llm_judge.build_messages_kwargs("q", "r")
    system = kw["system"]
    assert len(system) == 2
    # Rubric block carries cache_control, system message doesn't need it.
    assert system[1].get("cache_control") == {"type": "ephemeral"}
    assert kw["tool_choice"] == {"type": "tool", "name": "submit_scores"}
    assert kw["tools"][0]["name"] == "submit_scores"


def test_extract_tool_use_reads_input_from_dict_style_blocks():
    resp = {
        "content": [
            {"type": "text", "text": "reasoning..."},
            {
                "type": "tool_use",
                "name": "submit_scores",
                "input": {
                    "relevance": 4, "citation_quality": 3,
                    "hallucination": 0, "reasoning": "ok",
                },
            },
        ],
    }
    got = llm_judge.extract_tool_use(resp)
    assert got == {
        "relevance": 4, "citation_quality": 3,
        "hallucination": 0, "reasoning": "ok",
    }


def test_extract_tool_use_reads_input_from_object_style_blocks():
    """Real anthropic SDK returns objects with attributes, not dicts."""
    block = SimpleNamespace(
        type="tool_use",
        name="submit_scores",
        input={"relevance": 5, "citation_quality": 5, "hallucination": 0, "reasoning": "x"},
    )
    resp = SimpleNamespace(content=[block])
    got = llm_judge.extract_tool_use(resp)
    assert got["relevance"] == 5


def test_extract_tool_use_raises_when_judge_replies_with_text_only():
    resp = {"content": [{"type": "text", "text": "I refuse to grade"}]}
    with pytest.raises(ValueError, match="did not emit a submit_scores"):
        llm_judge.extract_tool_use(resp)


def test_score_one_builds_and_parses_end_to_end():
    captured: dict = {}

    def _fake_call(**kwargs):
        captured.update(kwargs)
        return {
            "content": [
                {
                    "type": "tool_use",
                    "name": "submit_scores",
                    "input": {
                        "relevance": 5, "citation_quality": 4,
                        "hallucination": 0, "reasoning": "clear answer with sources",
                    },
                },
            ],
        }

    sc = llm_judge.score_one(
        qid="q042",
        query="what is 2+2?",
        response="4. See https://x.com.",
        call_messages_create=_fake_call,
    )
    assert sc.id == "q042"
    assert sc.relevance == 5
    assert sc.citation_quality == 4
    assert sc.hallucination == 0
    assert sc.reasoning.startswith("clear")
    assert captured["model"] == llm_judge.DEFAULT_JUDGE_MODEL
    assert captured["tool_choice"] == {"type": "tool", "name": "submit_scores"}


def test_make_default_caller_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm_judge.make_default_caller()
