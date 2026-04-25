"""End-to-end test for `analyze.py`: feed synthetic fixtures, check outputs."""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

import pytest

EVALS_ROOT = Path(__file__).resolve().parent.parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

import analyze  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _prepare_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "demo"
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / "heuristics_sample.jsonl", run_dir / "heuristics.jsonl")
    shutil.copy(FIXTURES / "llm_scores_sample.jsonl", run_dir / "llm_scores.jsonl")
    return run_dir


def test_run_analyze_happy_path(tmp_path):
    run_dir = _prepare_run_dir(tmp_path)
    # Point dataset path at a file that doesn't exist — analyze should still work
    # because heuristics.jsonl already carries labels.
    result = analyze.run_analyze(
        run_dir,
        dataset_path=tmp_path / "nope.jsonl",
        now=datetime(2026, 4, 21, 9, 30, 15),
    )
    assert result["summary_path"].exists()
    assert result["metrics_path"].name == "metrics_20260421_093015.csv"
    assert result["scores_path"].name == "scores_20260421_093015.csv"
    assert result["n_rows"] == 30
    assert result["n_scores"] == 10


def test_run_analyze_overwrites_summary_but_preserves_csvs(tmp_path):
    run_dir = _prepare_run_dir(tmp_path)
    # First run.
    analyze.run_analyze(run_dir, dataset_path=tmp_path / "nope.jsonl",
                        now=datetime(2026, 4, 21, 9, 30, 15))
    # Second run with a different timestamp.
    analyze.run_analyze(run_dir, dataset_path=tmp_path / "nope.jsonl",
                        now=datetime(2026, 4, 21, 10, 0, 0))
    csv_files = sorted(run_dir.glob("metrics_*.csv"))
    assert len(csv_files) == 2, f"expected history to accumulate, got {csv_files}"
    # summary.md is only the latest → single file.
    assert (run_dir / "summary.md").exists()
    assert len(list(run_dir.glob("summary*.md"))) == 1


def test_run_analyze_missing_heuristics_raises(tmp_path):
    run_dir = tmp_path / "runs" / "empty"
    run_dir.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        analyze.run_analyze(run_dir, dataset_path=tmp_path / "whatever.jsonl")


def test_run_analyze_without_llm_scores(tmp_path):
    run_dir = tmp_path / "runs" / "no_llm"
    run_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "heuristics_sample.jsonl", run_dir / "heuristics.jsonl")
    # No llm_scores.jsonl — analyze must tolerate this.
    result = analyze.run_analyze(run_dir, dataset_path=tmp_path / "nope.jsonl",
                                 now=datetime(2026, 4, 21, 0, 0, 0))
    assert result["n_scores"] == 0
    summary = result["summary_path"].read_text(encoding="utf-8")
    assert "未启用 LLM 裁判" in summary


def test_main_returns_2_when_run_dir_missing(capsys, tmp_path):
    rc = analyze.main(["--run-dir", str(tmp_path / "ghost")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "run dir not found" in err


def test_main_green_path_prints_summary_line(capsys, tmp_path):
    run_dir = _prepare_run_dir(tmp_path)
    rc = analyze.main([
        "--run-dir", str(run_dir),
        "--dataset", str(tmp_path / "nope.jsonl"),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "summary" in out
    assert "n_rows=30" in out
