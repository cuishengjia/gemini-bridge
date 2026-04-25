"""Pure aggregation over a run's heuristics + llm_scores.

All functions are side-effect-free and work on plain `dict` rows so callers
can feed them anything JSON-shaped — heuristics.jsonl lines, llm_scores.jsonl
lines, or in-memory synthetic fixtures.

Design principles:
- No pandas / numpy. stdlib `statistics` + careful percentile.
- Every function returns `None` (or an empty dict) for degenerate inputs
  instead of raising, so the render layer can show "-" without branching
  on every edge case.
- "Stratification" = bucketing by one of: time_sensitivity, domain, difficulty.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

Number = int | float

# Dimensions callers can slice by. Keep this list ordered for stable output.
STRATIFICATION_DIMENSIONS: tuple[str, ...] = ("time_sensitivity", "domain", "difficulty")


# ---------- IO ----------


def load_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of dicts. Missing file → empty list."""
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


# ---------- small numeric helpers ----------


def _percentile(values: Sequence[Number], p: float) -> float | None:
    """Linear-interpolated percentile. `p` in [0, 100]. Returns None for empty input.

    We don't reuse `statistics.quantiles` because it can't cleanly produce p95
    at small n without tripping `StatisticsError`.
    """
    if not values:
        return None
    if not 0 <= p <= 100:
        raise ValueError(f"percentile p must be in [0, 100], got {p}")
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    frac = k - lo
    return float(xs[lo] + (xs[hi] - xs[lo]) * frac)


def _safe_mean(values: Sequence[Number]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


# ---------- row filtering ----------


def _ok_rows(rows: Iterable[dict]) -> list[dict]:
    """Rows that came back clean (no synthetic error envelope)."""
    return [r for r in rows if r.get("ok") is True]


# ---------- overall ----------


@dataclass(frozen=True)
class OverallStats:
    total: int
    ok_count: int
    ok_rate: float | None
    fallback_count: int
    fallback_rate: float | None
    mean_attempts: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "ok_count": self.ok_count,
            "ok_rate": self.ok_rate,
            "fallback_count": self.fallback_count,
            "fallback_rate": self.fallback_rate,
            "mean_attempts": self.mean_attempts,
        }


def overall_stats(rows: Sequence[dict]) -> OverallStats:
    total = len(rows)
    ok_count = sum(1 for r in rows if r.get("ok") is True)
    fallback_count = sum(1 for r in rows if r.get("fallback_triggered") is True)
    attempts = [int(r.get("attempts_count") or 0) for r in rows]
    return OverallStats(
        total=total,
        ok_count=ok_count,
        ok_rate=_safe_rate(ok_count, total),
        fallback_count=fallback_count,
        fallback_rate=_safe_rate(fallback_count, total),
        mean_attempts=_safe_mean(attempts),
    )


# ---------- error categories / model usage ----------


def error_category_distribution(rows: Sequence[dict]) -> dict[str, int]:
    """Counts of envelope.error.category among non-ok rows. ok rows are skipped."""
    counts: dict[str, int] = {}
    for r in rows:
        if r.get("ok") is True:
            continue
        cat = r.get("error_category") or "unknown"
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def model_used_distribution(rows: Sequence[dict]) -> dict[str, int]:
    """Counts of model_used across ok rows. Missing model is bucketed as 'unknown'."""
    counts: dict[str, int] = {}
    for r in _ok_rows(rows):
        m = r.get("model_used") or "unknown"
        counts[m] = counts.get(m, 0) + 1
    return counts


# ---------- bucket slices ----------


@dataclass(frozen=True)
class BucketStat:
    bucket: str
    n: int
    ok_count: int
    ok_rate: float | None
    mean_wall_ms: float | None
    mean_url_count: float | None
    refusal_rate: float | None
    short_response_rate: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "n": self.n,
            "ok_count": self.ok_count,
            "ok_rate": self.ok_rate,
            "mean_wall_ms": self.mean_wall_ms,
            "mean_url_count": self.mean_url_count,
            "refusal_rate": self.refusal_rate,
            "short_response_rate": self.short_response_rate,
        }


def bucket_stats(rows: Sequence[dict], dimension: str) -> list[BucketStat]:
    """Slice rows by `dimension` and compute per-bucket stats.

    The bucket key is stringified (even for `difficulty`) so callers can emit
    tables without branching on type.
    """
    if dimension not in STRATIFICATION_DIMENSIONS:
        raise ValueError(
            f"dimension must be one of {STRATIFICATION_DIMENSIONS}, got {dimension!r}"
        )

    groups: dict[str, list[dict]] = {}
    for r in rows:
        key = str(r.get(dimension, "") or "")
        groups.setdefault(key, []).append(r)

    out: list[BucketStat] = []
    for bucket in sorted(groups.keys()):
        bucket_rows = groups[bucket]
        n = len(bucket_rows)
        ok_count = sum(1 for r in bucket_rows if r.get("ok") is True)
        ok_rows = _ok_rows(bucket_rows)

        wall = [int(r.get("wall_ms") or 0) for r in ok_rows if r.get("wall_ms") is not None]
        urls = [int(r.get("url_count") or 0) for r in ok_rows]
        refusals = sum(1 for r in ok_rows if r.get("refusal_hit") is True)
        shorts = sum(1 for r in ok_rows if r.get("short_response") is True)

        out.append(
            BucketStat(
                bucket=bucket,
                n=n,
                ok_count=ok_count,
                ok_rate=_safe_rate(ok_count, n),
                mean_wall_ms=_safe_mean(wall),
                mean_url_count=_safe_mean(urls),
                refusal_rate=_safe_rate(refusals, len(ok_rows)),
                short_response_rate=_safe_rate(shorts, len(ok_rows)),
            )
        )
    return out


# ---------- token stats ----------


def _distribution(values: Sequence[Number]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "sum": 0, "mean": None, "p50": None, "p95": None}
    return {
        "n": len(values),
        "sum": sum(values),
        "mean": _safe_mean(values),
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
    }


def token_stats(rows: Sequence[dict]) -> dict[str, dict[str, float | int | None]]:
    """Return sum/mean/p50/p95 per token axis (input/output/total).

    Only ok rows contribute — synthetic error envelopes don't carry tokens.
    """
    ok = _ok_rows(rows)
    return {
        "input": _distribution([int(r.get("input_tokens") or 0) for r in ok]),
        "output": _distribution([int(r.get("output_tokens") or 0) for r in ok]),
        "total": _distribution([int(r.get("total_tokens") or 0) for r in ok]),
    }


# ---------- search calls ----------


def search_call_distribution(rows: Sequence[dict]) -> dict[str, Any]:
    """Histogram + mean of google_web_search calls across ok rows."""
    ok = _ok_rows(rows)
    calls = [int(r.get("google_search_calls") or 0) for r in ok]
    histogram: dict[int, int] = {}
    for c in calls:
        histogram[c] = histogram.get(c, 0) + 1
    return {
        "n": len(calls),
        "mean": _safe_mean(calls),
        "p50": _percentile(calls, 50),
        "p95": _percentile(calls, 95),
        # Sort histogram keys ascending for stable rendering.
        "histogram": {k: histogram[k] for k in sorted(histogram.keys())},
    }


# ---------- LLM judge stats ----------


def llm_score_stats(
    scores: Sequence[dict],
    rows_by_id: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Overall + per-time_sensitivity breakdown of judge scores.

    `rows_by_id` maps heuristics id → heuristics row (or dataset row) so we
    can cross-tab scores by the query's time_sensitivity. If the mapping is
    missing or incomplete, the cross-tab for that row is skipped.
    """
    if not scores:
        return {
            "n": 0,
            "overall": {},
            "by_time_sensitivity": {},
        }

    def _axis_stats(values: Sequence[Number]) -> dict[str, float | None]:
        return {
            "mean": _safe_mean(values),
            "p50": _percentile(values, 50),
            "p95": _percentile(values, 95),
        }

    relevance = [int(s.get("relevance") or 0) for s in scores]
    citation = [int(s.get("citation_quality") or 0) for s in scores]
    hallucination = [int(s.get("hallucination") or 0) for s in scores]

    overall = {
        "relevance": _axis_stats(relevance),
        "citation_quality": _axis_stats(citation),
        "hallucination_rate": _safe_mean(hallucination),  # 0/1 → proportion
    }

    by_ts: dict[str, dict[str, Any]] = {}
    if rows_by_id:
        grouped: dict[str, list[dict]] = {}
        for s in scores:
            sid = s.get("id")
            if not sid:
                continue
            row = rows_by_id.get(sid)
            if not row:
                continue
            ts = str(row.get("time_sensitivity") or "unknown")
            grouped.setdefault(ts, []).append(s)

        for ts in sorted(grouped.keys()):
            grp = grouped[ts]
            by_ts[ts] = {
                "n": len(grp),
                "relevance": _axis_stats([int(s.get("relevance") or 0) for s in grp]),
                "citation_quality": _axis_stats(
                    [int(s.get("citation_quality") or 0) for s in grp]
                ),
                "hallucination_rate": _safe_mean(
                    [int(s.get("hallucination") or 0) for s in grp]
                ),
            }

    return {
        "n": len(scores),
        "overall": overall,
        "by_time_sensitivity": by_ts,
    }


# ---------- edge-case samples (for "warnings" section of report) ----------


def top_slow(rows: Sequence[dict], n: int = 5) -> list[dict]:
    """Top-N slowest ok rows by wall_ms, descending."""
    ok = _ok_rows(rows)
    ok_sorted = sorted(ok, key=lambda r: int(r.get("wall_ms") or 0), reverse=True)
    return ok_sorted[:n]


def zero_url_ok_rows(rows: Sequence[dict]) -> list[dict]:
    """ok rows that produced no URL — suspicious for research mode."""
    return [r for r in _ok_rows(rows) if (r.get("url_count") or 0) == 0]


def refusal_ok_rows(rows: Sequence[dict]) -> list[dict]:
    """ok rows flagged as refusals by the heuristic — the model gave up."""
    return [r for r in _ok_rows(rows) if r.get("refusal_hit") is True]
