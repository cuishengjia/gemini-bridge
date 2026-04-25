"""Unit tests for evals.lib.aggregate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVALS_ROOT = Path(__file__).resolve().parent.parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from lib.aggregate import (  # noqa: E402
    STRATIFICATION_DIMENSIONS,
    _percentile,
    bucket_stats,
    error_category_distribution,
    llm_score_stats,
    load_jsonl,
    model_used_distribution,
    overall_stats,
    refusal_ok_rows,
    search_call_distribution,
    token_stats,
    top_slow,
    zero_url_ok_rows,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HEUR_PATH = FIXTURES / "heuristics_sample.jsonl"
SCORES_PATH = FIXTURES / "llm_scores_sample.jsonl"


# ---------- _percentile ----------


def test_percentile_empty_returns_none():
    assert _percentile([], 50) is None


def test_percentile_single_value():
    assert _percentile([7], 50) == 7.0
    assert _percentile([7], 95) == 7.0


def test_percentile_linear_interpolation():
    # For [1,2,3,4,5], p50 at k=2 is exactly 3.
    assert _percentile([1, 2, 3, 4, 5], 50) == 3.0
    # p0 is the min, p100 is the max.
    assert _percentile([1, 2, 3, 4, 5], 0) == 1.0
    assert _percentile([1, 2, 3, 4, 5], 100) == 5.0


def test_percentile_rejects_out_of_range():
    with pytest.raises(ValueError):
        _percentile([1, 2], -1)
    with pytest.raises(ValueError):
        _percentile([1, 2], 101)


# ---------- IO ----------


def test_load_jsonl_missing_returns_empty(tmp_path):
    assert load_jsonl(tmp_path / "nope.jsonl") == []


def test_load_jsonl_reads_fixtures():
    rows = load_jsonl(HEUR_PATH)
    assert len(rows) == 30
    scores = load_jsonl(SCORES_PATH)
    assert len(scores) == 10


# ---------- overall_stats ----------


def test_overall_stats_on_fixture():
    rows = load_jsonl(HEUR_PATH)
    st = overall_stats(rows)
    assert st.total == 30
    # 26 ok, 4 failures in fixture (q009/q010/q018/q025).
    assert st.ok_count == 26
    assert st.ok_rate == pytest.approx(26 / 30)
    # 4 fallback-triggered (q003/q008/q013/q022).
    assert st.fallback_count == 4
    assert st.fallback_rate == pytest.approx(4 / 30)
    # attempts should average below 2.
    assert 1.0 < st.mean_attempts < 2.0


def test_overall_stats_empty():
    st = overall_stats([])
    assert st.total == 0
    assert st.ok_rate is None
    assert st.mean_attempts is None


# ---------- error_category_distribution ----------


def test_error_category_distribution():
    rows = load_jsonl(HEUR_PATH)
    dist = error_category_distribution(rows)
    assert dist == {
        "timeout": 1,
        "quota_exhausted": 1,
        "malformed_output": 1,
        "auth": 1,
    }


def test_error_category_distribution_none_category_becomes_unknown():
    rows = [{"ok": False, "error_category": None}]
    assert error_category_distribution(rows) == {"unknown": 1}


# ---------- model_used_distribution ----------


def test_model_used_distribution_only_counts_ok_rows():
    rows = load_jsonl(HEUR_PATH)
    dist = model_used_distribution(rows)
    # 3-pro dominates; 2.5-pro used on 3 (q003/q013/q022); flash on 1 (q008).
    assert dist["gemini-3-pro-preview"] == 22
    assert dist["gemini-2.5-pro"] == 3
    assert dist["gemini-2.5-flash"] == 1
    # 4 failed rows should NOT appear here.
    assert sum(dist.values()) == 26


# ---------- bucket_stats ----------


def test_bucket_stats_by_time_sensitivity():
    rows = load_jsonl(HEUR_PATH)
    buckets = bucket_stats(rows, "time_sensitivity")
    by_name = {b.bucket: b for b in buckets}
    assert set(by_name.keys()) == {"strong", "medium", "evergreen_obscure", "evergreen_common"}

    strong = by_name["strong"]
    assert strong.n == 10
    # 8 ok in strong (q001-q008), 2 failures (q009/q010).
    assert strong.ok_count == 8
    assert strong.ok_rate == pytest.approx(0.8)
    # q008 is the only refusal in strong, out of 8 ok rows.
    assert strong.refusal_rate == pytest.approx(1 / 8)
    # mean_wall_ms comes from ok rows only, so failed 120s/5s don't pull it up.
    assert strong.mean_wall_ms is not None
    assert strong.mean_wall_ms < 30000


def test_bucket_stats_by_domain_sorted_deterministically():
    rows = load_jsonl(HEUR_PATH)
    buckets = bucket_stats(rows, "domain")
    # Keys are sorted alphabetically.
    assert [b.bucket for b in buckets] == sorted(b.bucket for b in buckets)


def test_bucket_stats_rejects_bad_dimension():
    with pytest.raises(ValueError):
        bucket_stats([], "not_a_dimension")


def test_bucket_stats_knows_allowed_dimensions():
    assert STRATIFICATION_DIMENSIONS == ("time_sensitivity", "domain", "difficulty")


def test_bucket_stats_empty_bucket_has_none_rates():
    # All rows failed → ok_rate is 0/0 → None, not a crash.
    rows = [
        {"time_sensitivity": "x", "ok": False, "wall_ms": 0, "url_count": 0,
         "refusal_hit": False, "short_response": True},
    ]
    [b] = bucket_stats(rows, "time_sensitivity")
    assert b.ok_rate == 0.0  # 0/1, not None — denominator is bucket size, not ok count
    assert b.mean_wall_ms is None  # no ok rows → no wall values
    assert b.refusal_rate is None  # no ok rows → can't compute


# ---------- token_stats ----------


def test_token_stats_only_counts_ok_rows():
    rows = load_jsonl(HEUR_PATH)
    t = token_stats(rows)
    # 26 ok rows contribute.
    assert t["input"]["n"] == 26
    assert t["output"]["n"] == 26
    assert t["total"]["n"] == 26
    assert t["total"]["sum"] > 0
    assert t["total"]["p50"] is not None


def test_token_stats_empty_returns_zeros():
    t = token_stats([])
    assert t["input"] == {"n": 0, "sum": 0, "mean": None, "p50": None, "p95": None}


# ---------- search_call_distribution ----------


def test_search_call_distribution():
    rows = load_jsonl(HEUR_PATH)
    d = search_call_distribution(rows)
    assert d["n"] == 26
    assert d["mean"] is not None
    # histogram keys are ints sorted ascending; the fixture uses 1-4 calls.
    assert all(isinstance(k, int) for k in d["histogram"].keys())
    assert list(d["histogram"].keys()) == sorted(d["histogram"].keys())


# ---------- llm_score_stats ----------


def test_llm_score_stats_on_fixture():
    scores = load_jsonl(SCORES_PATH)
    rows = load_jsonl(HEUR_PATH)
    rows_by_id = {r["id"]: r for r in rows}
    stats = llm_score_stats(scores, rows_by_id)
    assert stats["n"] == 10
    # 1 hallucination in 10 → rate 0.1.
    assert stats["overall"]["hallucination_rate"] == pytest.approx(0.1)
    # relevance mean should be above 4 given the fixture.
    assert stats["overall"]["relevance"]["mean"] > 4.0
    # by_time_sensitivity should include strong/medium/evergreen_obscure/evergreen_common.
    assert set(stats["by_time_sensitivity"].keys()) == {
        "strong", "medium", "evergreen_obscure", "evergreen_common",
    }


def test_llm_score_stats_empty():
    stats = llm_score_stats([], {})
    assert stats["n"] == 0
    assert stats["overall"] == {}


def test_llm_score_stats_without_rows_by_id_skips_cross_tab():
    scores = load_jsonl(SCORES_PATH)
    stats = llm_score_stats(scores, None)
    assert stats["n"] == 10
    assert stats["by_time_sensitivity"] == {}


# ---------- edge-case samples ----------


def test_top_slow_returns_n_slowest_ok_rows():
    rows = load_jsonl(HEUR_PATH)
    slow = top_slow(rows, n=3)
    assert len(slow) == 3
    wall_times = [r["wall_ms"] for r in slow]
    assert wall_times == sorted(wall_times, reverse=True)
    # q009 failed (120s) should NOT be included despite being the largest wall_ms.
    assert all(r["ok"] is True for r in slow)


def test_zero_url_ok_rows():
    rows = load_jsonl(HEUR_PATH)
    zeros = zero_url_ok_rows(rows)
    # q024 is ok but has 0 URLs in the fixture.
    assert any(r["id"] == "q024" for r in zeros)
    assert all(r["ok"] is True for r in zeros)


def test_refusal_ok_rows():
    rows = load_jsonl(HEUR_PATH)
    refusals = refusal_ok_rows(rows)
    # q008 is the sole refusal in the fixture.
    assert [r["id"] for r in refusals] == ["q008"]
