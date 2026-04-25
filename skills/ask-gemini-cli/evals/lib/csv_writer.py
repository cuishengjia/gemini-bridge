"""Timestamped CSV export for a run's metrics and judge scores.

Why two files:
- `metrics_<ts>.csv` — one row per envelope (all 200). Primary artifact
  for downstream spreadsheet analysis.
- `scores_<ts>.csv`  — one row per LLM-judged sample (up to 50), joined
  with stratification labels so you can pivot by time_sensitivity/domain.

Both are written with a YYYYMMDD_HHMMSS timestamp so re-running analyze
never overwrites history (only summary.md is treated as "latest").
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

METRICS_COLUMNS: tuple[str, ...] = (
    "id",
    "ok",
    "model_used",
    "fallback_triggered",
    "attempts_count",
    "error_category",
    "wall_ms",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "response_len",
    "url_count",
    "has_url",
    "refusal_hit",
    "short_response",
    "google_search_calls",
    "total_tool_calls",
    "time_sensitivity",
    "domain",
    "difficulty",
)

SCORES_COLUMNS: tuple[str, ...] = (
    "id",
    "time_sensitivity",
    "domain",
    "difficulty",
    "relevance",
    "citation_quality",
    "hallucination",
    "judge_model",
    "reasoning",
)


def timestamp(now: datetime | None = None) -> str:
    """YYYYMMDD_HHMMSS. `now` injectable for deterministic tests."""
    return (now or datetime.now()).strftime("%Y%m%d_%H%M%S")


def _serialize(value: Any) -> str:
    """Render CSV cells with stable formatting.

    - None → empty string (pandas reads it as NaN).
    - bool → "true"/"false" (spreadsheets reading "True" sometimes coerce
      to Python-string; lowercase is less surprising in Sheets/Excel).
    - everything else → str(value).
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_metrics_csv(rows: Sequence[dict], out_path: Path) -> Path:
    """Write heuristics rows to CSV. Returns the path for chaining."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(METRICS_COLUMNS)
        for r in rows:
            writer.writerow([_serialize(r.get(c)) for c in METRICS_COLUMNS])
    return out_path


def write_scores_csv(
    scores: Sequence[dict],
    rows_by_id: dict[str, dict],
    out_path: Path,
) -> Path:
    """Write judge scores joined with stratification labels."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(SCORES_COLUMNS)
        for s in scores:
            sid = s.get("id")
            row = rows_by_id.get(sid or "") or {}
            merged = {
                "id": sid,
                "time_sensitivity": row.get("time_sensitivity"),
                "domain": row.get("domain"),
                "difficulty": row.get("difficulty"),
                "relevance": s.get("relevance"),
                "citation_quality": s.get("citation_quality"),
                "hallucination": s.get("hallucination"),
                "judge_model": s.get("judge_model"),
                "reasoning": s.get("reasoning"),
            }
            writer.writerow([_serialize(merged[c]) for c in SCORES_COLUMNS])
    return out_path


def write_timestamped_csvs(
    rows: Sequence[dict],
    scores: Sequence[dict],
    rows_by_id: dict[str, dict],
    out_dir: Path,
    now: datetime | None = None,
) -> tuple[Path, Path]:
    """Write both CSVs with a shared timestamp. Returns (metrics_path, scores_path)."""
    ts = timestamp(now)
    metrics_path = out_dir / f"metrics_{ts}.csv"
    scores_path = out_dir / f"scores_{ts}.csv"
    write_metrics_csv(rows, metrics_path)
    write_scores_csv(scores, rows_by_id, scores_path)
    return metrics_path, scores_path
