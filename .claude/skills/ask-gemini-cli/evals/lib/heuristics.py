"""Heuristic signals extracted from a single research-mode envelope.

All functions are pure and independent of network / Claude API so the
whole module can be unit-tested offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

URL_REGEX = re.compile(
    r"https?://[^\s<>\"\'\)\]]+(?<![.,;:!?])",
    re.IGNORECASE,
)

# Refusal / give-up phrases. Lowercased-compare; covers EN + ZH.
REFUSAL_PATTERNS: tuple[str, ...] = (
    "i don't know",
    "i do not know",
    "i'm not sure",
    "i am not sure",
    "cannot find",
    "could not find",
    "can't find",
    "unable to find",
    "no results",
    "insufficient information",
    "not enough information",
    "我不知道",
    "无法找到",
    "找不到",
    "没有找到",
    "信息不足",
)

SHORT_RESPONSE_CHAR_THRESHOLD: int = 100


@dataclass(frozen=True)
class Heuristics:
    """Flattened signal row. One per envelope."""

    id: str
    ok: bool
    model_used: str | None
    fallback_triggered: bool
    error_category: str | None
    wall_ms: int
    attempts_count: int
    response_len: int
    url_count: int
    has_url: bool
    refusal_hit: bool
    short_response: bool
    google_search_calls: int
    total_tool_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    time_sensitivity: str
    domain: str
    difficulty: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ok": self.ok,
            "model_used": self.model_used,
            "fallback_triggered": self.fallback_triggered,
            "error_category": self.error_category,
            "wall_ms": self.wall_ms,
            "attempts_count": self.attempts_count,
            "response_len": self.response_len,
            "url_count": self.url_count,
            "has_url": self.has_url,
            "refusal_hit": self.refusal_hit,
            "short_response": self.short_response,
            "google_search_calls": self.google_search_calls,
            "total_tool_calls": self.total_tool_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "time_sensitivity": self.time_sensitivity,
            "domain": self.domain,
            "difficulty": self.difficulty,
        }


def extract_urls(text: str | None) -> list[str]:
    if not text:
        return []
    return URL_REGEX.findall(text)


def is_refusal(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(p in lowered for p in REFUSAL_PATTERNS)


def is_short_response(text: str | None, *, threshold: int = SHORT_RESPONSE_CHAR_THRESHOLD) -> bool:
    """Short = genuine content under threshold chars. Missing text is not 'short', it's empty."""
    if not text:
        return True
    return len(text.strip()) < threshold


def count_google_search_calls(tool_calls: list[dict] | None) -> int:
    if not tool_calls:
        return 0
    return sum(
        1 for tc in tool_calls
        if isinstance(tc, dict) and tc.get("name") == "google_web_search"
    )


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def compute_heuristics(envelope: dict, *, query_meta: dict | None = None) -> Heuristics:
    """Collapse one envelope + its source query-row into a single Heuristics.

    `query_meta` brings the time_sensitivity / domain / difficulty labels from
    the dataset so downstream analysis can stratify without re-joining.
    """
    qid = envelope.get("_runner", {}).get("id") or (query_meta or {}).get("id", "")
    ok = bool(envelope.get("ok"))
    model_used = envelope.get("model_used")
    fallback = bool(envelope.get("fallback_triggered", False))
    error = envelope.get("error") or {}
    error_category = error.get("category") if isinstance(error, dict) else None

    response = envelope.get("response") or ""
    urls = extract_urls(response)

    tool_calls = envelope.get("tool_calls") or []
    stats = envelope.get("stats") or {}
    attempts = envelope.get("attempts") or []

    meta = query_meta or {}
    return Heuristics(
        id=qid,
        ok=ok,
        model_used=model_used,
        fallback_triggered=fallback,
        error_category=error_category,
        wall_ms=_as_int(envelope.get("_runner", {}).get("wall_ms")),
        attempts_count=len(attempts),
        response_len=len(response),
        url_count=len(urls),
        has_url=bool(urls),
        refusal_hit=is_refusal(response),
        short_response=is_short_response(response),
        google_search_calls=count_google_search_calls(tool_calls),
        total_tool_calls=len(tool_calls) if isinstance(tool_calls, list) else 0,
        input_tokens=_as_int(stats.get("input_tokens")),
        output_tokens=_as_int(stats.get("output_tokens")),
        total_tokens=_as_int(stats.get("total_tokens")),
        time_sensitivity=str(meta.get("time_sensitivity", "")),
        domain=str(meta.get("domain", "")),
        difficulty=_as_int(meta.get("difficulty")),
    )
