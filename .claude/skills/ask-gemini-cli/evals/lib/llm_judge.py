"""Claude-backed LLM judge for research-mode responses.

Design notes:
- The judge is a different model family (Claude) than the system under
  evaluation (Gemini), which is the whole point — homogeneous judging
  would just echo the generator's biases.
- The rubric prompt is held stable and cached so repeated invocations
  reuse the prompt cache (see `judge_response` cache_control block).
- The judge is forced to emit structured JSON via tool use so parsing
  never touches free-form prose.
- The Anthropic SDK is imported lazily so offline tests can mock the
  entire `call_claude_judge` surface without installing the package.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Protocol

DEFAULT_JUDGE_MODEL: str = "claude-opus-4-7"

SYSTEM_PROMPT: str = (
    "You are an impartial evaluator scoring a research-mode AI assistant's "
    "answer to a user query. You are NOT the assistant — do not answer the "
    "query yourself. Apply the rubric strictly and emit your verdict via the "
    "`submit_scores` tool. Never speculate beyond what the provided answer "
    "contains."
)

RUBRIC: str = """\
Score the assistant's answer on three axes.

1. relevance (1–5): How well does the answer address the user's query?
   - 5: Directly and completely answers the query.
   - 4: Answers the main point; minor gaps or tangents.
   - 3: Partially answers; misses key sub-questions.
   - 2: Mostly off-topic or very superficial.
   - 1: Does not answer the query at all.

2. citation_quality (1–5): Are the cited URLs credible and consistent with the claims?
   - 5: Multiple reputable URLs clearly backing each factual claim.
   - 4: At least one reputable URL per major claim; minor gaps OK.
   - 3: URLs present but coverage is uneven or authority is mixed.
   - 2: Few URLs, or URLs appear unrelated / low quality.
   - 1: No URLs, or URLs are obviously fabricated/broken.

3. hallucination (0 or 1): Does the answer contain a plausibly-false factual claim
   that is not supported by the cited sources or is internally contradictory?
   - 0: No such claim detected.
   - 1: At least one apparent hallucination.

Be strict. When in doubt on hallucination, mark 1 and explain briefly.
"""

JUDGE_TOOL: dict[str, Any] = {
    "name": "submit_scores",
    "description": "Submit the final rubric scores for the assistant's answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "relevance": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "How well the answer addresses the query (1–5).",
            },
            "citation_quality": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Reliability and alignment of cited URLs (1–5).",
            },
            "hallucination": {
                "type": "integer",
                "minimum": 0,
                "maximum": 1,
                "description": "1 if any claim appears fabricated or unsupported, else 0.",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief 1–3 sentence justification referencing specific parts of the answer.",
            },
        },
        "required": ["relevance", "citation_quality", "hallucination", "reasoning"],
    },
}


@dataclass(frozen=True)
class LlmScore:
    id: str
    relevance: int
    citation_quality: int
    hallucination: int
    reasoning: str
    judge_model: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "relevance": self.relevance,
            "citation_quality": self.citation_quality,
            "hallucination": self.hallucination,
            "reasoning": self.reasoning,
            "judge_model": self.judge_model,
        }


class ClaudeClient(Protocol):
    """Minimal surface of `anthropic.Anthropic` we depend on, for mocking."""

    def messages_create(self, **kwargs: Any) -> Any: ...  # pragma: no cover


def build_user_message(query: str, response: str) -> str:
    """User-turn content. Query and answer are clearly delimited."""
    response_clean = response.strip() if response else "(empty response)"
    return (
        f"<user_query>\n{query.strip()}\n</user_query>\n\n"
        f"<assistant_answer>\n{response_clean}\n</assistant_answer>\n\n"
        "Apply the rubric above and call `submit_scores`."
    )


def extract_tool_use(message_response: Any) -> dict[str, Any]:
    """Pull the `submit_scores` tool_use block out of a Messages API response.

    Raises ValueError if the judge didn't call the tool — which is the signal
    to either retry or discard the sample, not to silently accept a text reply.
    """
    content = getattr(message_response, "content", None) or message_response.get("content", [])
    for block in content:
        btype = getattr(block, "type", None) if not isinstance(block, dict) else block.get("type")
        if btype == "tool_use":
            bname = getattr(block, "name", None) if not isinstance(block, dict) else block.get("name")
            binput = getattr(block, "input", None) if not isinstance(block, dict) else block.get("input")
            if bname == "submit_scores" and isinstance(binput, dict):
                return binput
    raise ValueError("judge did not emit a submit_scores tool_use block")


def build_messages_kwargs(
    query: str,
    response: str,
    *,
    model: str = DEFAULT_JUDGE_MODEL,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """Kwargs for `client.messages.create(...)`.

    The system prompt + rubric are marked `cache_control: ephemeral` so the
    Anthropic prompt cache absorbs the rubric tokens across calls.
    """
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": [
            {"type": "text", "text": SYSTEM_PROMPT},
            {
                "type": "text",
                "text": RUBRIC,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        "tools": [JUDGE_TOOL],
        "tool_choice": {"type": "tool", "name": "submit_scores"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_user_message(query, response)},
                ],
            }
        ],
    }


def score_one(
    qid: str,
    query: str,
    response: str,
    *,
    call_messages_create: Callable[..., Any],
    model: str = DEFAULT_JUDGE_MODEL,
) -> LlmScore:
    """One judged sample. Network call is injected so tests can pass a fake."""
    kwargs = build_messages_kwargs(query, response, model=model)
    raw = call_messages_create(**kwargs)
    scores = extract_tool_use(raw)
    return LlmScore(
        id=qid,
        relevance=int(scores["relevance"]),
        citation_quality=int(scores["citation_quality"]),
        hallucination=int(scores["hallucination"]),
        reasoning=str(scores.get("reasoning", "")),
        judge_model=model,
    )


def make_default_caller(api_key: str | None = None) -> Callable[..., Any]:
    """Build a `call_messages_create` closure that dispatches to Anthropic.

    Imports the SDK lazily so modules that never actually call a judge
    (e.g. running only heuristics) don't need anthropic installed at all.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set and no api_key argument provided"
        )
    import anthropic  # local import — see docstring

    client = anthropic.Anthropic(api_key=key)

    def _call(**kwargs: Any) -> Any:
        return client.messages.create(**kwargs)

    return _call


def score_to_jsonl_line(score: LlmScore) -> str:
    return json.dumps(score.to_dict(), ensure_ascii=False)
