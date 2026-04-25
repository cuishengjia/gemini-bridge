"""Judge a completed run: heuristics on all 200 + Claude LLM-judge on 50.

Reads `<run-dir>/envelopes/*.json` and the source dataset (for labels),
emits:
  <run-dir>/heuristics.jsonl   — one row per envelope (all 200)
  <run-dir>/llm_scores.jsonl   — one row per sampled envelope (n=50)
  <run-dir>/judge_manifest.json — which ids were sampled, seed, model

The LLM sample is stratified 20/15/10/5 across the four time_sensitivity
buckets (mirrors pilot logic so numbers stay comparable).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

EVALS_ROOT = Path(__file__).resolve().parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from lib.heuristics import Heuristics, compute_heuristics  # noqa: E402
from lib.llm_judge import (  # noqa: E402
    DEFAULT_JUDGE_MODEL,
    LlmScore,
    make_default_caller,
    score_one,
    score_to_jsonl_line,
)
from lib.schema import QueryRow, load_jsonl  # noqa: E402

# LLM-judge sample plan (n=50 total, mirrors dataset 80:60:40:20).
LLM_SAMPLE_PLAN: dict[str, int] = {
    "strong": 20,
    "medium": 15,
    "evergreen_obscure": 10,
    "evergreen_common": 5,
}


@dataclass
class JudgeSummary:
    heuristics_count: int
    llm_scored_count: int
    llm_failed_count: int
    sampled_ids: list[str]


def load_envelope(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def collect_envelopes(run_dir: Path) -> dict[str, dict]:
    """Return {id: envelope} for every JSON in envelopes/."""
    out: dict[str, dict] = {}
    env_dir = run_dir / "envelopes"
    for path in sorted(env_dir.glob("*.json")):
        env = load_envelope(path)
        qid = env.get("_runner", {}).get("id") or path.stem
        out[qid] = env
    return out


def compute_all_heuristics(
    envelopes: dict[str, dict],
    rows_by_id: dict[str, QueryRow],
) -> list[Heuristics]:
    hs: list[Heuristics] = []
    for qid, env in envelopes.items():
        row = rows_by_id.get(qid)
        meta = {
            "id": qid,
            "time_sensitivity": row.time_sensitivity if row else "",
            "domain": row.domain if row else "",
            "difficulty": row.difficulty if row else 0,
        }
        hs.append(compute_heuristics(env, query_meta=meta))
    hs.sort(key=lambda h: h.id)
    return hs


def write_heuristics_jsonl(heuristics: list[Heuristics], path: Path) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for h in heuristics:
            fh.write(json.dumps(h.to_dict(), ensure_ascii=False) + "\n")


def pick_llm_sample(
    heuristics: list[Heuristics],
    rows_by_id: dict[str, QueryRow],
    *,
    plan: dict[str, int] = LLM_SAMPLE_PLAN,
    seed: int = 0,
    only_ok: bool = True,
) -> list[str]:
    """Stratified 20/15/10/5 id list. Only ok envelopes are eligible by default
    since judging a synthetic error envelope yields no signal.
    """
    pool_by_bucket: dict[str, list[str]] = {}
    for h in heuristics:
        if only_ok and not h.ok:
            continue
        row = rows_by_id.get(h.id)
        if not row:
            continue
        pool_by_bucket.setdefault(row.time_sensitivity, []).append(h.id)

    rng = random.Random(seed)
    picked: list[str] = []
    for bucket, n in plan.items():
        pool = pool_by_bucket.get(bucket, [])
        take = min(n, len(pool))
        if take < n:
            print(
                f"warn: bucket {bucket!r} has {len(pool)} eligible ok samples, "
                f"plan asked for {n} — sampling {take}",
                file=sys.stderr,
            )
        picked.extend(rng.sample(pool, take))

    picked.sort()
    return picked


def judge_sample(
    sample_ids: list[str],
    envelopes: dict[str, dict],
    rows_by_id: dict[str, QueryRow],
    *,
    call_messages_create: Callable,
    model: str,
    retry: int = 1,
    sleep_between_s: float = 0.3,
) -> tuple[list[LlmScore], list[tuple[str, str]]]:
    """Judge every sampled id. Returns (scores, failures).

    `failures` is a list of (id, error_message) for sampled rows where the
    judge failed after all retries — downstream analysis can decide whether
    to re-sample or drop from aggregates.
    """
    scores: list[LlmScore] = []
    failures: list[tuple[str, str]] = []

    for i, qid in enumerate(sample_ids, 1):
        env = envelopes[qid]
        row = rows_by_id[qid]
        response = env.get("response") or ""

        last_err = ""
        for attempt in range(retry + 1):
            try:
                sc = score_one(
                    qid=qid,
                    query=row.query,
                    response=response,
                    call_messages_create=call_messages_create,
                    model=model,
                )
                scores.append(sc)
                print(
                    f"[{i}/{len(sample_ids)}] {qid} rel={sc.relevance} "
                    f"cite={sc.citation_quality} halluc={sc.hallucination}",
                    flush=True,
                )
                break
            except Exception as e:  # noqa: BLE001 — judge failures shouldn't kill the batch
                last_err = f"{type(e).__name__}: {e}"
                if attempt < retry:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                failures.append((qid, last_err))
                print(f"[{i}/{len(sample_ids)}] {qid} JUDGE_FAIL {last_err}", flush=True)

        if sleep_between_s:
            time.sleep(sleep_between_s)

    return scores, failures


def write_llm_scores_jsonl(scores: list[LlmScore], path: Path) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for s in scores:
            fh.write(score_to_jsonl_line(s) + "\n")


def write_judge_manifest(
    run_dir: Path,
    *,
    sample_ids: list[str],
    failures: list[tuple[str, str]],
    seed: int,
    model: str,
    plan: dict[str, int],
) -> None:
    manifest = {
        "judged_at": datetime.now().isoformat(timespec="seconds"),
        "judge_model": model,
        "seed": seed,
        "plan": plan,
        "sampled_ids": sample_ids,
        "failures": [{"id": i, "error": e} for i, e in failures],
    }
    (run_dir / "judge_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------- CLI ----------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--dataset", type=Path,
                    default=EVALS_ROOT / "datasets" / "research_200.jsonl")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--llm-model", default=DEFAULT_JUDGE_MODEL)
    ap.add_argument("--skip-llm", action="store_true",
                    help="Compute heuristics only; skip Claude judging.")
    ap.add_argument("--retry", type=int, default=1)
    ap.add_argument("--include-failed-in-sample", action="store_true",
                    help="Judge even ok=false envelopes (default: skip them).")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not args.run_dir.exists():
        print(f"run dir not found: {args.run_dir}", file=sys.stderr)
        return 2
    if not args.dataset.exists():
        print(f"dataset not found: {args.dataset}", file=sys.stderr)
        return 2

    rows = load_jsonl(args.dataset)
    rows_by_id = {r.id: r for r in rows}

    envelopes = collect_envelopes(args.run_dir)
    if not envelopes:
        print(f"no envelopes under {args.run_dir}/envelopes", file=sys.stderr)
        return 2
    print(f"loaded {len(envelopes)} envelopes from {args.run_dir}")

    heuristics = compute_all_heuristics(envelopes, rows_by_id)
    heur_path = args.run_dir / "heuristics.jsonl"
    write_heuristics_jsonl(heuristics, heur_path)
    print(f"wrote {len(heuristics)} heuristic rows to {heur_path}")

    if args.skip_llm:
        print("skipping LLM-judge (--skip-llm)")
        return 0

    sample_ids = pick_llm_sample(
        heuristics,
        rows_by_id,
        seed=args.seed,
        only_ok=not args.include_failed_in_sample,
    )
    print(f"sampled {len(sample_ids)} ids for LLM-judge")

    try:
        caller = make_default_caller()
    except RuntimeError as e:
        print(f"LLM-judge disabled: {e}", file=sys.stderr)
        return 3

    scores, failures = judge_sample(
        sample_ids,
        envelopes,
        rows_by_id,
        call_messages_create=caller,
        model=args.llm_model,
        retry=args.retry,
    )

    scores_path = args.run_dir / "llm_scores.jsonl"
    write_llm_scores_jsonl(scores, scores_path)
    write_judge_manifest(
        args.run_dir,
        sample_ids=sample_ids,
        failures=failures,
        seed=args.seed,
        model=args.llm_model,
        plan=LLM_SAMPLE_PLAN,
    )

    print("\n=== judge summary ===")
    print(f"  heuristics: {len(heuristics)}")
    print(f"  llm scored: {len(scores)}")
    print(f"  llm failed: {len(failures)}")
    print(f"  scores → {scores_path}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
