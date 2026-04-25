"""Unit tests for evals.lib.report."""

from __future__ import annotations

import sys
from pathlib import Path

EVALS_ROOT = Path(__file__).resolve().parent.parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from lib.aggregate import load_jsonl  # noqa: E402
from lib.report import render_summary  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HEUR_PATH = FIXTURES / "heuristics_sample.jsonl"
SCORES_PATH = FIXTURES / "llm_scores_sample.jsonl"


def test_render_summary_contains_expected_sections():
    rows = load_jsonl(HEUR_PATH)
    scores = load_jsonl(SCORES_PATH)
    md = render_summary(rows, scores, meta={"run_dir": "runs/demo"})
    assert "# Research-mode 评测报告" in md
    assert "一、总体概览" in md
    assert "二、错误分布" in md
    assert "按 time_sensitivity 分层" in md
    assert "按 domain 分层" in md
    assert "按 difficulty 分层" in md
    assert "token 消耗" in md
    assert "google_web_search" in md
    assert "model_used" in md
    assert "LLM 裁判分数" in md
    assert "异常样本提示" in md


def test_render_summary_empty_scores_shows_fallback():
    rows = load_jsonl(HEUR_PATH)
    md = render_summary(rows, scores=[], meta={"run_dir": "runs/demo"})
    assert "未启用 LLM 裁判" in md


def test_render_summary_empty_rows_still_renders():
    md = render_summary(rows=[], scores=[])
    # No crash; total is 0; all sections gracefully degrade.
    assert "样本总数：0" in md
    assert "无失败样本" in md or "错误分布" in md


def test_render_summary_formats_rates_as_percent():
    rows = load_jsonl(HEUR_PATH)
    md = render_summary(rows, scores=[])
    # ok_rate = 26/30 ≈ 86.7%. Look for "86.7%" presence.
    assert "86.7%" in md


def test_render_summary_puts_run_dir_into_header():
    md = render_summary(rows=[], scores=[], meta={"run_dir": "runs/pilot_xyz"})
    assert "runs/pilot_xyz" in md


def test_render_summary_handles_missing_meta():
    # Should still render with generated_at default.
    md = render_summary(rows=[], scores=[])
    assert "生成时间：" in md


def test_render_summary_slow_table_includes_ok_only():
    rows = load_jsonl(HEUR_PATH)
    md = render_summary(rows, scores=[])
    # q009 is the failed timeout (120s) — it must NOT appear in the slow table.
    slow_section = md.split("最慢 5 条")[1] if "最慢 5 条" in md else ""
    # The section should exist for a non-empty ok set.
    assert slow_section
    assert "q009" not in slow_section


def test_render_summary_time_sensitivity_bucket_rates():
    rows = load_jsonl(HEUR_PATH)
    md = render_summary(rows, scores=[])
    # strong bucket in fixture has ok_rate 80%.
    assert "strong" in md
    assert "80.0%" in md  # appears at least once (strong bucket ok_rate)


def test_render_summary_llm_cross_tab_when_scores_present():
    rows = load_jsonl(HEUR_PATH)
    scores = load_jsonl(SCORES_PATH)
    md = render_summary(rows, scores)
    assert "按 time_sensitivity 分层" in md  # also appears as bucket header
    # The LLM cross-tab subsection should include per-bucket stats.
    llm_section = md.split("LLM 裁判分数")[1]
    assert "strong" in llm_section
    assert "medium" in llm_section
