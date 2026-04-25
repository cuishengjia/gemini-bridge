#!/usr/bin/env python3
"""Generate per-query summary CSV from a runner result directory.

Usage:
    python3 evals/make_csv.py <run_dir> [dataset_path]

Outputs <run_dir>/per_query_summary.csv with one row per envelope.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s)\"'<>]+")


def load_dataset(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            rows[d["id"]] = d
    return rows


def envelope_to_row(qid: str, env: dict, ds: dict) -> dict:
    ok = env.get("ok", False)
    model = env.get("model_used") or ""
    fallback = env.get("fallback_triggered", False)
    stats = env.get("stats") or {}
    wall_ms = stats.get("wall_ms") or 0
    wall_s = round(wall_ms / 1000, 1)
    response = env.get("response") or ""
    resp_chars = len(response)
    url_count = len(URL_RE.findall(response))
    tool_calls = env.get("tool_calls") or []
    n_tools = len(tool_calls)
    warnings = env.get("warnings") or []
    w_str = "|".join(warnings) if warnings else ""
    error = env.get("error") or {}
    err_kind = error.get("kind") if isinstance(error, dict) else ""
    query = ds.get("query", "")
    preview = query[:80].replace("\n", " ")
    return {
        "id": qid,
        "bucket": ds.get("difficulty", ""),
        "time_sensitivity": ds.get("time_sensitivity", ""),
        "domain": ds.get("domain", ""),
        "ok": "1" if ok else "0",
        "model": model,
        "fallback": "1" if fallback else "0",
        "wall_s": wall_s,
        "resp_chars": resp_chars,
        "url_count": url_count,
        "tool_calls": n_tools,
        "warnings": w_str,
        "error_kind": err_kind or "",
        "query_preview": preview,
        "query": query,
        "response": response,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: make_csv.py <run_dir> [dataset_path]", file=sys.stderr)
        sys.exit(2)
    run_dir = Path(sys.argv[1])
    ds_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else run_dir.parent.parent / "datasets" / "research_200.jsonl"
    if not ds_path.exists():
        # Fallback: read dataset path from manifest
        man = run_dir / "manifest.json"
        if man.exists():
            data = json.loads(man.read_text())
            ds_path = Path(data["dataset"])
    ds_rows = load_dataset(ds_path)

    env_dir = run_dir / "envelopes"
    files = sorted(env_dir.glob("q*.json"))
    out_path = run_dir / "per_query_summary.csv"

    fieldnames = [
        "id", "bucket", "time_sensitivity", "domain", "ok", "model",
        "fallback", "wall_s", "resp_chars", "url_count", "tool_calls",
        "warnings", "error_kind", "query_preview", "query", "response",
    ]

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for f in files:
            qid = f.stem
            try:
                env = json.loads(f.read_text())
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] failed to parse {f}: {exc}", file=sys.stderr)
                continue
            ds = ds_rows.get(qid, {})
            writer.writerow(envelope_to_row(qid, env, ds))

    print(f"wrote {out_path} ({len(files)} rows)")


if __name__ == "__main__":
    main()
