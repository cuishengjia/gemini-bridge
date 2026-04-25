"""Unit tests for evals.lib.csv_writer."""

from __future__ import annotations

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

EVALS_ROOT = Path(__file__).resolve().parent.parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from lib.aggregate import load_jsonl  # noqa: E402
from lib.csv_writer import (  # noqa: E402
    METRICS_COLUMNS,
    SCORES_COLUMNS,
    _serialize,
    timestamp,
    write_metrics_csv,
    write_scores_csv,
    write_timestamped_csvs,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HEUR_PATH = FIXTURES / "heuristics_sample.jsonl"
SCORES_PATH = FIXTURES / "llm_scores_sample.jsonl"

TIMESTAMP_RE = re.compile(r"^\d{8}_\d{6}$")


def test_timestamp_matches_format():
    ts = timestamp(datetime(2026, 4, 21, 9, 30, 15))
    assert ts == "20260421_093015"


def test_timestamp_default_now_format():
    assert TIMESTAMP_RE.match(timestamp())


def test_serialize_none_becomes_empty_string():
    assert _serialize(None) == ""


def test_serialize_bool_lowercase():
    assert _serialize(True) == "true"
    assert _serialize(False) == "false"


def test_serialize_numbers_and_strings():
    assert _serialize(42) == "42"
    assert _serialize(3.14) == "3.14"
    assert _serialize("hello") == "hello"


def test_write_metrics_csv_headers_and_row_count(tmp_path):
    rows = load_jsonl(HEUR_PATH)
    out = tmp_path / "metrics.csv"
    write_metrics_csv(rows, out)
    assert out.exists()
    with out.open() as fh:
        reader = csv.reader(fh)
        header = next(reader)
        data_rows = list(reader)
    assert tuple(header) == METRICS_COLUMNS
    assert len(data_rows) == 30


def test_write_metrics_csv_bool_serialization(tmp_path):
    rows = load_jsonl(HEUR_PATH)
    out = tmp_path / "metrics.csv"
    write_metrics_csv(rows, out)
    text = out.read_text()
    # ok column is serialized as lowercase.
    assert "true" in text
    assert "false" in text
    # No raw Python True/False in the file.
    assert "True," not in text
    assert "False," not in text


def test_write_metrics_csv_none_becomes_empty_cell(tmp_path):
    # Failed envelope has model_used=None; it should render as empty, not "None".
    rows = [
        {"id": "x", "ok": False, "model_used": None, "fallback_triggered": False,
         "attempts_count": 1, "error_category": "auth", "wall_ms": 0,
         "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
         "response_len": 0, "url_count": 0, "has_url": False,
         "refusal_hit": False, "short_response": True,
         "google_search_calls": 0, "total_tool_calls": 0,
         "time_sensitivity": "strong", "domain": "tech", "difficulty": 1}
    ]
    out = tmp_path / "metrics.csv"
    write_metrics_csv(rows, out)
    with out.open() as fh:
        reader = csv.DictReader(fh)
        row = next(reader)
    assert row["model_used"] == ""


def test_write_scores_csv_joins_labels(tmp_path):
    scores = load_jsonl(SCORES_PATH)
    rows = load_jsonl(HEUR_PATH)
    rows_by_id = {r["id"]: r for r in rows}
    out = tmp_path / "scores.csv"
    write_scores_csv(scores, rows_by_id, out)
    with out.open() as fh:
        reader = csv.DictReader(fh)
        data = list(reader)
    assert len(data) == 10
    # Join worked: q001 should have time_sensitivity=strong, domain=tech.
    q001 = next(r for r in data if r["id"] == "q001")
    assert q001["time_sensitivity"] == "strong"
    assert q001["domain"] == "tech"
    assert q001["relevance"] == "5"
    assert q001["hallucination"] == "0"


def test_write_scores_csv_unknown_id_gets_empty_labels(tmp_path):
    scores = [{"id": "ghost", "relevance": 5, "citation_quality": 5,
               "hallucination": 0, "reasoning": "x", "judge_model": "claude-opus-4-7"}]
    out = tmp_path / "scores.csv"
    write_scores_csv(scores, rows_by_id={}, out_path=out)
    with out.open() as fh:
        reader = csv.DictReader(fh)
        [row] = list(reader)
    assert row["time_sensitivity"] == ""
    assert row["domain"] == ""
    assert row["relevance"] == "5"


def test_write_scores_csv_header_order():
    assert SCORES_COLUMNS[0] == "id"
    assert SCORES_COLUMNS[-1] == "reasoning"


def test_write_timestamped_csvs_produces_both(tmp_path):
    rows = load_jsonl(HEUR_PATH)
    scores = load_jsonl(SCORES_PATH)
    rows_by_id = {r["id"]: r for r in rows}
    m_path, s_path = write_timestamped_csvs(
        rows, scores, rows_by_id, tmp_path,
        now=datetime(2026, 4, 21, 9, 30, 15),
    )
    assert m_path.name == "metrics_20260421_093015.csv"
    assert s_path.name == "scores_20260421_093015.csv"
    assert m_path.exists() and s_path.exists()


def test_write_timestamped_csvs_creates_parent(tmp_path):
    rows = load_jsonl(HEUR_PATH)
    target_dir = tmp_path / "nested" / "runs"
    # Intentionally no mkdir — writer should create parents.
    write_timestamped_csvs(rows, [], {}, target_dir,
                           now=datetime(2026, 4, 21, 0, 0, 0))
    assert target_dir.exists()
    assert (target_dir / "metrics_20260421_000000.csv").exists()
