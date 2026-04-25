"""Aggregate a run into summary.md + timestamped CSVs.

Reads `<run-dir>/heuristics.jsonl` and `<run-dir>/llm_scores.jsonl`
(produced by `judge.py`), joins with the source dataset for stratification
labels, and emits:

  <run-dir>/summary.md                      — overwritten each run (latest)
  <run-dir>/metrics_<YYYYMMDD_HHMMSS>.csv   — timestamped history
  <run-dir>/scores_<YYYYMMDD_HHMMSS>.csv    — timestamped history

`summary.md` is deliberately the only "latest" pointer — CSVs accumulate
so you can diff successive runs without losing prior data.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

EVALS_ROOT = Path(__file__).resolve().parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from lib.aggregate import load_jsonl, overall_stats  # noqa: E402
from lib.csv_writer import write_timestamped_csvs  # noqa: E402
from lib.report import render_summary  # noqa: E402
from lib.schema import load_jsonl as load_dataset  # noqa: E402

HEURISTICS_FILE = "heuristics.jsonl"
LLM_SCORES_FILE = "llm_scores.jsonl"
SUMMARY_FILE = "summary.md"


def _enrich_rows_with_labels(
    rows: list[dict],
    dataset_rows_by_id: dict,
) -> list[dict]:
    """Fill missing time_sensitivity / domain / difficulty by joining the dataset.

    heuristics.jsonl already has these labels (judge.py injects them), but
    belt-and-suspenders: if a row is missing them, fall back to dataset.
    """
    out = []
    for r in rows:
        if not r.get("time_sensitivity") or not r.get("domain"):
            dsr = dataset_rows_by_id.get(r.get("id"))
            if dsr is not None:
                r = {
                    **r,
                    "time_sensitivity": r.get("time_sensitivity") or dsr.time_sensitivity,
                    "domain": r.get("domain") or dsr.domain,
                    "difficulty": r.get("difficulty") or dsr.difficulty,
                }
        out.append(r)
    return out


def run_analyze(run_dir: Path, dataset_path: Path, now: datetime | None = None) -> dict:
    """Execute the full pipeline. Returns a small dict describing outputs.

    Raises FileNotFoundError if heuristics.jsonl is missing — that's a hard
    precondition, analyze makes no sense without it.
    """
    heur_path = run_dir / HEURISTICS_FILE
    if not heur_path.exists():
        raise FileNotFoundError(
            f"{heur_path} not found. Did you run `judge.py --run-dir {run_dir}` first?"
        )

    rows = load_jsonl(heur_path)
    scores = load_jsonl(run_dir / LLM_SCORES_FILE)  # missing → []

    dataset_rows_by_id: dict = {}
    if dataset_path.exists():
        dataset_rows_by_id = {r.id: r for r in load_dataset(dataset_path)}

    rows = _enrich_rows_with_labels(rows, dataset_rows_by_id)
    rows_by_id = {r["id"]: r for r in rows if "id" in r}

    metrics_path, scores_path = write_timestamped_csvs(
        rows, scores, rows_by_id, run_dir, now=now,
    )

    meta = {
        "run_dir": str(run_dir),
        "generated_at": (now or datetime.now()).isoformat(timespec="seconds"),
    }
    summary_md = render_summary(rows, scores, rows_by_id=rows_by_id, meta=meta)
    summary_path = run_dir / SUMMARY_FILE
    summary_path.write_text(summary_md, encoding="utf-8")

    st = overall_stats(rows)
    return {
        "summary_path": summary_path,
        "metrics_path": metrics_path,
        "scores_path": scores_path,
        "n_rows": st.total,
        "n_scores": len(scores),
        "ok_rate": st.ok_rate,
    }


# ---------- CLI ----------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument(
        "--dataset", type=Path,
        default=EVALS_ROOT / "datasets" / "research_200.jsonl",
        help="Source dataset for stratification labels.",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.run_dir.exists():
        print(f"run dir not found: {args.run_dir}", file=sys.stderr)
        return 2

    result = run_analyze(args.run_dir, args.dataset)
    print(f"summary  → {result['summary_path']}")
    print(f"metrics  → {result['metrics_path']}")
    print(f"scores   → {result['scores_path']}")
    print(
        f"n_rows={result['n_rows']} "
        f"n_scores={result['n_scores']} "
        f"ok_rate="
        + (f"{result['ok_rate'] * 100:.1f}%" if result["ok_rate"] is not None else "-")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
