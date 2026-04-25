"""Batch-call `bin/ask-gemini --mode research` over the locked dataset.

Writes one envelope per query to `results/run-<ts>/envelopes/<id>.json`.
Resumable: an existing envelope file is never overwritten, so a partial
run can be continued simply by re-pointing at the same `--run-dir`.

Design points:
- subprocess per query; each wall-timed independently (default 120s)
- concurrency via ThreadPoolExecutor (default 2 — OAuth-safe)
- one retry on timeout / non-zero exit / bad JSON; after that we persist
  a synthetic error envelope so downstream analyzers see every id
- pilot subsampling is stratified across time_sensitivity buckets to
  preserve the 80/60/40/20 ratio in miniature (default 20 → 8/6/4/2)
- deterministic: sampling uses a seeded `random.Random`
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

EVALS_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = EVALS_ROOT.parent
DEFAULT_ASK_GEMINI = SKILL_ROOT / "bin" / "ask-gemini"

if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from lib.schema import QueryRow, load_jsonl  # noqa: E402

# Pilot subsample preserves the 80:60:40:20 ratio — 8/6/4/2 at N=20.
PILOT_RATIO: dict[str, float] = {
    "strong": 0.40,
    "medium": 0.30,
    "evergreen_obscure": 0.20,
    "evergreen_common": 0.10,
}


@dataclass
class RunResult:
    """What happened to one query. Mirrors the envelope's shape superficially."""

    id: str
    ok: bool
    skipped: bool
    wall_ms: int
    model_used: str | None
    fallback_triggered: bool
    error_category: str | None
    attempts_total: int = 1  # local retries, not envelope.attempts
    notes: list[str] = field(default_factory=list)


# ---------- pure helpers ----------


def stratified_sample(
    rows: Sequence[QueryRow],
    n_total: int,
    *,
    ratio: dict[str, float] = PILOT_RATIO,
    seed: int = 0,
) -> list[QueryRow]:
    """Return n_total rows drawn from `rows`, keeping per-bucket ratios.

    The per-bucket count is `round(n_total * ratio[bucket])`; any drift
    from `n_total` is absorbed by the largest bucket so the output size
    matches exactly.
    """
    if n_total <= 0:
        raise ValueError("n_total must be positive")

    by_bucket: dict[str, list[QueryRow]] = {}
    for row in rows:
        by_bucket.setdefault(row.time_sensitivity, []).append(row)

    targets = {b: round(n_total * r) for b, r in ratio.items()}
    drift = n_total - sum(targets.values())
    if drift:
        biggest = max(targets, key=lambda b: targets[b])
        targets[biggest] += drift

    rng = random.Random(seed)
    picked: list[QueryRow] = []
    for bucket, count in targets.items():
        pool = by_bucket.get(bucket, [])
        if count > len(pool):
            raise ValueError(
                f"bucket {bucket!r} has {len(pool)} rows but pilot asks for {count}"
            )
        picked.extend(rng.sample(pool, count))

    picked.sort(key=lambda r: r.id)  # stable processing order
    return picked


def build_argv(ask_gemini: Path, query: str) -> list[str]:
    """Argv for a single research invocation. Deliberately minimal."""
    return [
        str(ask_gemini),
        "--mode",
        "research",
        "--query",
        query,
    ]


def parse_envelope(stdout: str) -> dict:
    """Parse ask-gemini's stdout (a single JSON line) into a dict."""
    stdout = stdout.strip()
    if not stdout:
        raise ValueError("empty stdout")
    return json.loads(stdout)


def error_envelope(row: QueryRow, category: str, message: str, wall_ms: int) -> dict:
    """Synthetic envelope used when we never got a real one from gemini."""
    return {
        "ok": False,
        "mode": "research",
        "model_used": None,
        "fallback_triggered": False,
        "attempts": [],
        "response": None,
        "stats": None,
        "tool_calls": [],
        "persisted_to": None,
        "warnings": [],
        "error": {
            "category": category,
            "message": message,
            "source": "runner",
        },
        "_runner": {
            "id": row.id,
            "wall_ms": wall_ms,
        },
    }


# ---------- single-query driver ----------


def run_one(
    row: QueryRow,
    *,
    ask_gemini: Path,
    run_dir: Path,
    timeout: int,
    retry: int,
) -> RunResult:
    """Run one query to completion (or exhausted retries) and persist the envelope.

    Idempotent: if the envelope file already exists, returns immediately with
    `skipped=True` and reads back the envelope to populate summary fields.
    """
    envelope_path = run_dir / "envelopes" / f"{row.id}.json"
    if envelope_path.exists():
        try:
            existing = json.loads(envelope_path.read_text("utf-8"))
        except Exception:
            existing = {}
        return RunResult(
            id=row.id,
            ok=bool(existing.get("ok")),
            skipped=True,
            wall_ms=int(existing.get("_runner", {}).get("wall_ms", 0)),
            model_used=existing.get("model_used"),
            fallback_triggered=bool(existing.get("fallback_triggered", False)),
            error_category=(existing.get("error") or {}).get("category"),
        )

    argv = build_argv(ask_gemini, row.query)
    last_category = "general"
    last_message = ""
    last_wall_ms = 0
    attempts_total = 0

    for attempt in range(retry + 1):
        attempts_total = attempt + 1
        start = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            wall_ms = int((time.monotonic() - start) * 1000)
            last_wall_ms = wall_ms

            if proc.returncode == 0:
                try:
                    envelope = parse_envelope(proc.stdout)
                except (ValueError, json.JSONDecodeError) as e:
                    last_category = "malformed_output"
                    last_message = f"unparseable stdout: {e}"
                    continue

                envelope.setdefault("_runner", {})
                envelope["_runner"]["id"] = row.id
                envelope["_runner"]["wall_ms"] = wall_ms
                envelope["_runner"]["attempts_total"] = attempts_total

                envelope_path.parent.mkdir(parents=True, exist_ok=True)
                envelope_path.write_text(
                    json.dumps(envelope, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                return RunResult(
                    id=row.id,
                    ok=bool(envelope.get("ok")),
                    skipped=False,
                    wall_ms=wall_ms,
                    model_used=envelope.get("model_used"),
                    fallback_triggered=bool(envelope.get("fallback_triggered", False)),
                    error_category=(envelope.get("error") or {}).get("category"),
                    attempts_total=attempts_total,
                )

            # non-zero exit — try to parse envelope anyway, often valid on bad_input
            try:
                envelope = parse_envelope(proc.stdout)
                envelope.setdefault("_runner", {})
                envelope["_runner"]["id"] = row.id
                envelope["_runner"]["wall_ms"] = wall_ms
                envelope["_runner"]["attempts_total"] = attempts_total
                envelope_path.parent.mkdir(parents=True, exist_ok=True)
                envelope_path.write_text(
                    json.dumps(envelope, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                return RunResult(
                    id=row.id,
                    ok=False,
                    skipped=False,
                    wall_ms=wall_ms,
                    model_used=envelope.get("model_used"),
                    fallback_triggered=bool(envelope.get("fallback_triggered", False)),
                    error_category=(envelope.get("error") or {}).get("category"),
                    attempts_total=attempts_total,
                )
            except Exception:
                last_category = "general"
                last_message = (
                    f"exit {proc.returncode}; stderr={proc.stderr[:500]!r}"
                )
                continue

        except subprocess.TimeoutExpired:
            wall_ms = int((time.monotonic() - start) * 1000)
            last_wall_ms = wall_ms
            last_category = "timeout"
            last_message = f"wall timeout after {timeout}s"
            continue

    envelope = error_envelope(row, last_category, last_message, last_wall_ms)
    envelope["_runner"]["attempts_total"] = attempts_total
    envelope_path.parent.mkdir(parents=True, exist_ok=True)
    envelope_path.write_text(
        json.dumps(envelope, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return RunResult(
        id=row.id,
        ok=False,
        skipped=False,
        wall_ms=last_wall_ms,
        model_used=None,
        fallback_triggered=False,
        error_category=last_category,
        attempts_total=attempts_total,
    )


# ---------- orchestration ----------


def run_batch(
    rows: Sequence[QueryRow],
    *,
    ask_gemini: Path,
    run_dir: Path,
    concurrency: int,
    timeout: int,
    retry: int,
    progress: bool = True,
) -> list[RunResult]:
    """Run every row with bounded concurrency; print progress lines as they finish."""
    (run_dir / "envelopes").mkdir(parents=True, exist_ok=True)

    results: list[RunResult] = []
    total = len(rows)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(
                run_one,
                row,
                ask_gemini=ask_gemini,
                run_dir=run_dir,
                timeout=timeout,
                retry=retry,
            ): row
            for row in rows
        }
        done = 0
        for fut in as_completed(futures):
            row = futures[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                res = RunResult(
                    id=row.id,
                    ok=False,
                    skipped=False,
                    wall_ms=0,
                    model_used=None,
                    fallback_triggered=False,
                    error_category="runner_crash",
                    notes=[repr(e)],
                )
            results.append(res)
            done += 1
            if progress:
                tag = "skip" if res.skipped else ("ok  " if res.ok else "FAIL")
                print(
                    f"[{done}/{total}] {res.id} {tag} "
                    f"wall={res.wall_ms}ms model={res.model_used or '-'} "
                    f"fallback={res.fallback_triggered} "
                    f"err={res.error_category or '-'}",
                    flush=True,
                )

    results.sort(key=lambda r: r.id)
    return results


def write_manifest(run_dir: Path, args: argparse.Namespace, dataset_path: Path,
                   rows: Iterable[QueryRow]) -> None:
    manifest = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "dataset": str(dataset_path),
        "dataset_rows": len(list(rows)),
        "concurrency": args.concurrency,
        "timeout_s": args.timeout,
        "retry": args.retry,
        "sample_pilot": args.sample_pilot,
        "seed": args.seed,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def summarize(results: Sequence[RunResult]) -> dict:
    """Partition into ok / skipped / failed so the three add up to total.

    Skipped envelopes come from an earlier run; counting them under `ok`
    would conflate "new success" with "already-known success" and make
    the progress signal misleading.
    """
    total = len(results)
    skipped = sum(1 for r in results if r.skipped)
    ok = sum(1 for r in results if r.ok and not r.skipped)
    failed = sum(1 for r in results if not r.ok and not r.skipped)
    fallback = sum(1 for r in results if r.fallback_triggered)
    return {
        "total": total,
        "ok": ok,
        "skipped": skipped,
        "failed": failed,
        "ok_rate": ok / total if total else 0.0,
        "fallback_rate": fallback / total if total else 0.0,
    }


# ---------- CLI ----------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Existing run dir to resume. If omitted, creates results/run-<ts>/.",
    )
    ap.add_argument("--sample-pilot", type=int, default=0,
                    help="If >0, take a stratified subsample of this size.")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument(
        "--timeout",
        type=int,
        default=480,
        help=(
            "Wall seconds per query. Must exceed the wrapper's primary-model budget "
            "(gemini-3-pro-preview = 300s in lib/fallback.py TIMEOUTS_S) so the "
            "wrapper's per-model timeout fires first and the fallback chain can "
            "actually engage. 480s = 300s (primary) + 180s (gemini-2.5-pro) — lets "
            "a one-step fallback complete. Pilot v1 used 120s and observed 0/6 "
            "fallbacks on timeouts: the outer runner killed the wrapper before the "
            "inner classifier ever saw timed_out=True."
        ),
    )
    ap.add_argument("--retry", type=int, default=1, help="Retry attempts on failure.")
    ap.add_argument("--seed", type=int, default=0, help="Sampling seed (pilot only).")
    ap.add_argument("--ask-gemini", type=Path, default=DEFAULT_ASK_GEMINI)
    ap.add_argument("--no-progress", action="store_true")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not args.dataset.exists():
        print(f"dataset not found: {args.dataset}", file=sys.stderr)
        return 2
    if not args.ask_gemini.exists():
        print(f"ask-gemini binary not found: {args.ask_gemini}", file=sys.stderr)
        return 2

    rows = load_jsonl(args.dataset)
    if args.sample_pilot and args.sample_pilot > 0:
        rows = stratified_sample(rows, args.sample_pilot, seed=args.seed)

    if args.run_dir is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = EVALS_ROOT / "results" / f"run-{ts}"
    else:
        run_dir = args.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(run_dir, args, args.dataset, rows)

    print(
        f"run_dir={run_dir}  queries={len(rows)}  concurrency={args.concurrency}  "
        f"timeout={args.timeout}s  retry={args.retry}",
        flush=True,
    )

    results = run_batch(
        rows,
        ask_gemini=args.ask_gemini,
        run_dir=run_dir,
        concurrency=args.concurrency,
        timeout=args.timeout,
        retry=args.retry,
        progress=not args.no_progress,
    )

    summary = summarize(results)
    print("\n=== summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    (run_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
