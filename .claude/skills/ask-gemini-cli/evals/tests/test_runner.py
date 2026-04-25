"""Unit tests for evals.runner.

subprocess and wall-clock are mocked so the suite stays offline and fast.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

EVALS_ROOT = Path(__file__).resolve().parent.parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

import runner  # noqa: E402
from lib.schema import QueryRow  # noqa: E402


def _row(id: str = "q001", query: str = "x", bucket: str = "strong",
         domain: str = "tech", diff: int = 1) -> QueryRow:
    return QueryRow(
        id=id, query=query, time_sensitivity=bucket,
        domain=domain, difficulty=diff, notes="",
    )


def _make_200_rows() -> list[QueryRow]:
    """Synthesize 200 rows with exact 80/60/40/20 bucket counts."""
    rows: list[QueryRow] = []
    counts = {"strong": 80, "medium": 60, "evergreen_obscure": 40, "evergreen_common": 20}
    idx = 1
    for bucket, n in counts.items():
        for _ in range(n):
            rows.append(_row(id=f"q{idx:03d}", bucket=bucket))
            idx += 1
    return rows


# ---------- stratified_sample ----------


def test_stratified_sample_preserves_ratio_at_n20():
    rows = _make_200_rows()
    sample = runner.stratified_sample(rows, 20, seed=0)
    assert len(sample) == 20
    from collections import Counter
    buckets = Counter(r.time_sensitivity for r in sample)
    assert buckets == {
        "strong": 8, "medium": 6,
        "evergreen_obscure": 4, "evergreen_common": 2,
    }


def test_stratified_sample_is_deterministic():
    rows = _make_200_rows()
    a = [r.id for r in runner.stratified_sample(rows, 20, seed=7)]
    b = [r.id for r in runner.stratified_sample(rows, 20, seed=7)]
    assert a == b


def test_stratified_sample_different_seeds_give_different_picks():
    rows = _make_200_rows()
    a = {r.id for r in runner.stratified_sample(rows, 20, seed=1)}
    b = {r.id for r in runner.stratified_sample(rows, 20, seed=2)}
    assert a != b


def test_stratified_sample_rejects_non_positive_n():
    with pytest.raises(ValueError):
        runner.stratified_sample(_make_200_rows(), 0)


def test_stratified_sample_rejects_too_large_bucket_ask():
    # Only 20 'evergreen_common' rows exist; asking for 100 overall forces >20 in that bucket.
    with pytest.raises(ValueError):
        runner.stratified_sample(_make_200_rows(), 400)


# ---------- build_argv ----------


def test_build_argv_is_minimal():
    argv = runner.build_argv(Path("/bin/ask-gemini"), "hello world")
    assert argv == [
        "/bin/ask-gemini", "--mode", "research", "--query", "hello world",
    ]


# ---------- parse_envelope ----------


def test_parse_envelope_accepts_valid_json():
    env = runner.parse_envelope('{"ok": true}')
    assert env == {"ok": True}


def test_parse_envelope_rejects_empty():
    with pytest.raises(ValueError):
        runner.parse_envelope("   ")


def test_parse_envelope_rejects_garbage():
    with pytest.raises(json.JSONDecodeError):
        runner.parse_envelope("not json")


# ---------- error_envelope ----------


def test_error_envelope_shape():
    row = _row()
    env = runner.error_envelope(row, "timeout", "wall 120s", 120_000)
    assert env["ok"] is False
    assert env["error"]["category"] == "timeout"
    assert env["_runner"]["id"] == row.id
    assert env["_runner"]["wall_ms"] == 120_000


# ---------- run_one (subprocess mocked) ----------


@pytest.fixture
def tmp_run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run-test"
    (d / "envelopes").mkdir(parents=True)
    return d


def _stub_completed(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def test_run_one_success_writes_envelope(monkeypatch, tmp_run_dir: Path):
    row = _row()
    payload = {
        "ok": True,
        "mode": "research",
        "model_used": "gemini-3-pro-preview",
        "fallback_triggered": False,
        "attempts": [{"model": "gemini-3-pro-preview", "exit_code": 0, "duration_ms": 123}],
        "response": "hi",
        "stats": {"total_tokens": 100},
        "tool_calls": [],
        "persisted_to": None,
        "warnings": [],
    }
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda *a, **kw: _stub_completed(json.dumps(payload)),
    )
    res = runner.run_one(row, ask_gemini=Path("/bin/ask-gemini"),
                        run_dir=tmp_run_dir, timeout=120, retry=1)
    assert res.ok is True
    assert res.skipped is False
    assert res.model_used == "gemini-3-pro-preview"
    saved = json.loads((tmp_run_dir / "envelopes" / "q001.json").read_text())
    assert saved["_runner"]["id"] == "q001"
    assert saved["_runner"]["attempts_total"] == 1


def test_run_one_skips_existing(monkeypatch, tmp_run_dir: Path):
    row = _row()
    existing = {
        "ok": True, "model_used": "gemini-2.5-pro",
        "fallback_triggered": True, "error": None,
        "_runner": {"id": "q001", "wall_ms": 4500},
    }
    (tmp_run_dir / "envelopes" / "q001.json").write_text(json.dumps(existing))

    called = {"count": 0}

    def _raise(*a, **kw):
        called["count"] += 1
        raise AssertionError("subprocess should not be invoked on resume")

    monkeypatch.setattr(runner.subprocess, "run", _raise)
    res = runner.run_one(row, ask_gemini=Path("/bin/ask-gemini"),
                        run_dir=tmp_run_dir, timeout=120, retry=1)
    assert res.skipped is True
    assert res.ok is True
    assert res.model_used == "gemini-2.5-pro"
    assert res.fallback_triggered is True
    assert called["count"] == 0


def test_run_one_retries_on_bad_json(monkeypatch, tmp_run_dir: Path):
    row = _row()
    payload = {
        "ok": True, "mode": "research", "model_used": "gemini-3-pro-preview",
        "fallback_triggered": False, "attempts": [], "response": "ok",
        "stats": None, "tool_calls": [], "persisted_to": None, "warnings": [],
    }
    calls = iter([
        _stub_completed("not json at all"),        # first attempt — malformed
        _stub_completed(json.dumps(payload)),      # retry — good
    ])
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **kw: next(calls))

    res = runner.run_one(row, ask_gemini=Path("/bin/ask-gemini"),
                        run_dir=tmp_run_dir, timeout=120, retry=1)
    assert res.ok is True
    assert res.attempts_total == 2


def test_run_one_timeout_writes_error_envelope(monkeypatch, tmp_run_dir: Path):
    row = _row()

    def _timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=a[0] if a else [], timeout=kw.get("timeout", 0))

    monkeypatch.setattr(runner.subprocess, "run", _timeout)
    res = runner.run_one(row, ask_gemini=Path("/bin/ask-gemini"),
                        run_dir=tmp_run_dir, timeout=1, retry=1)
    assert res.ok is False
    assert res.error_category == "timeout"
    saved = json.loads((tmp_run_dir / "envelopes" / "q001.json").read_text())
    assert saved["error"]["category"] == "timeout"
    assert saved["_runner"]["attempts_total"] == 2  # exhausted 1+1


def test_run_one_nonzero_but_valid_envelope(monkeypatch, tmp_run_dir: Path):
    """Gemini sometimes exits nonzero but still emits a proper error envelope."""
    row = _row()
    payload = {
        "ok": False, "mode": "research", "model_used": None,
        "fallback_triggered": False, "attempts": [], "response": None,
        "stats": None, "tool_calls": [], "persisted_to": None, "warnings": [],
        "error": {"category": "bad_input", "message": "empty query"},
    }
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda *a, **kw: _stub_completed(json.dumps(payload), returncode=3),
    )
    res = runner.run_one(row, ask_gemini=Path("/bin/ask-gemini"),
                        run_dir=tmp_run_dir, timeout=120, retry=0)
    assert res.ok is False
    assert res.error_category == "bad_input"
    saved = json.loads((tmp_run_dir / "envelopes" / "q001.json").read_text())
    assert saved["error"]["category"] == "bad_input"


# ---------- summarize ----------


def test_summarize_counts_correctly():
    results = [
        runner.RunResult(id="a", ok=True, skipped=False, wall_ms=100,
                         model_used="m", fallback_triggered=False, error_category=None),
        runner.RunResult(id="b", ok=True, skipped=True, wall_ms=200,
                         model_used="m", fallback_triggered=True, error_category=None),
        runner.RunResult(id="c", ok=False, skipped=False, wall_ms=300,
                         model_used=None, fallback_triggered=False, error_category="timeout"),
    ]
    s = runner.summarize(results)
    assert s["total"] == 3
    assert s["ok"] == 1  # only non-skipped ok
    assert s["skipped"] == 1
    assert s["failed"] == 1
    assert s["fallback_rate"] == pytest.approx(1 / 3)


# ---------- run_batch smoke ----------


def test_run_batch_processes_all_rows(monkeypatch, tmp_run_dir: Path):
    rows = [_row(id=f"q{i:03d}") for i in range(1, 6)]
    payload = {
        "ok": True, "mode": "research", "model_used": "gemini-3-pro-preview",
        "fallback_triggered": False, "attempts": [], "response": "ok",
        "stats": None, "tool_calls": [], "persisted_to": None, "warnings": [],
    }
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda *a, **kw: _stub_completed(json.dumps(payload)),
    )
    results = runner.run_batch(
        rows, ask_gemini=Path("/bin/ask-gemini"), run_dir=tmp_run_dir,
        concurrency=2, timeout=60, retry=0, progress=False,
    )
    assert [r.id for r in results] == [f"q{i:03d}" for i in range(1, 6)]
    assert all(r.ok for r in results)
    for i in range(1, 6):
        assert (tmp_run_dir / "envelopes" / f"q{i:03d}.json").exists()
