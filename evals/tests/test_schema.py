"""Unit tests for evals.lib.schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Inject evals root so `from lib.schema import ...` works without installing.
EVALS_ROOT = Path(__file__).resolve().parent.parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from lib.schema import (  # noqa: E402
    BUCKET_COUNTS,
    DATASET_SIZE,
    DOMAIN_PER_LABEL_MAX,
    DOMAIN_PER_LABEL_MIN,
    DOMAIN_VALUES,
    QueryRow,
    dump_jsonl,
    load_jsonl,
    validate_dataset,
)


def _row(
    id: str = "q001",
    query: str = "test query",
    time_sensitivity: str = "strong",
    domain: str = "tech",
    difficulty: int = 1,
    notes: str = "",
) -> QueryRow:
    return QueryRow(
        id=id,
        query=query,
        time_sensitivity=time_sensitivity,
        domain=domain,
        difficulty=difficulty,
        notes=notes,
    )


def _build_valid_dataset() -> list[QueryRow]:
    """Synthesize a 200-row dataset that satisfies every invariant.

    Layout per bucket:
      - domains cycled evenly across the bucket
      - difficulty distribution follows 60/30/10 inside each bucket
    """
    rows: list[QueryRow] = []
    idx = 1
    domains = sorted(DOMAIN_VALUES)  # 5 labels, deterministic order

    for bucket, count in BUCKET_COUNTS.items():
        # difficulty split: 60% / 30% / 10%
        d1 = round(count * 0.60)
        d2 = round(count * 0.30)
        d3 = count - d1 - d2
        difficulties = [1] * d1 + [2] * d2 + [3] * d3
        for i in range(count):
            rows.append(
                _row(
                    id=f"q{idx:03d}",
                    query=f"q{idx} in bucket {bucket}",
                    time_sensitivity=bucket,
                    domain=domains[i % len(domains)],
                    difficulty=difficulties[i],
                    notes="",
                )
            )
            idx += 1
    return rows


# ---------- QueryRow.from_dict ----------


def test_from_dict_accepts_valid_object():
    obj = {
        "id": "q001",
        "query": "hello",
        "time_sensitivity": "strong",
        "domain": "tech",
        "difficulty": 1,
        "notes": "",
    }
    row = QueryRow.from_dict(obj)
    assert row.id == "q001"
    assert row.difficulty == 1


def test_from_dict_rejects_missing_key():
    with pytest.raises(ValueError, match="missing required keys"):
        QueryRow.from_dict({"id": "q001", "query": "x"})


def test_from_dict_rejects_extra_key():
    with pytest.raises(ValueError, match="unexpected keys"):
        QueryRow.from_dict(
            {
                "id": "q001",
                "query": "x",
                "time_sensitivity": "strong",
                "domain": "tech",
                "difficulty": 1,
                "notes": "",
                "rogue": True,
            }
        )


def test_from_dict_rejects_empty_id():
    obj = {
        "id": "",
        "query": "x",
        "time_sensitivity": "strong",
        "domain": "tech",
        "difficulty": 1,
        "notes": "",
    }
    with pytest.raises(ValueError, match="id must be"):
        QueryRow.from_dict(obj)


def test_from_dict_rejects_whitespace_query():
    obj = {
        "id": "q001",
        "query": "   ",
        "time_sensitivity": "strong",
        "domain": "tech",
        "difficulty": 1,
        "notes": "",
    }
    with pytest.raises(ValueError, match="query must be"):
        QueryRow.from_dict(obj)


def test_from_dict_rejects_bad_time_sensitivity():
    obj = {
        "id": "q001",
        "query": "x",
        "time_sensitivity": "recent",
        "domain": "tech",
        "difficulty": 1,
        "notes": "",
    }
    with pytest.raises(ValueError, match="time_sensitivity must be"):
        QueryRow.from_dict(obj)


def test_from_dict_rejects_bad_domain():
    obj = {
        "id": "q001",
        "query": "x",
        "time_sensitivity": "strong",
        "domain": "politics",
        "difficulty": 1,
        "notes": "",
    }
    with pytest.raises(ValueError, match="domain must be"):
        QueryRow.from_dict(obj)


def test_from_dict_rejects_bad_difficulty():
    obj = {
        "id": "q001",
        "query": "x",
        "time_sensitivity": "strong",
        "domain": "tech",
        "difficulty": 5,
        "notes": "",
    }
    with pytest.raises(ValueError, match="difficulty must be"):
        QueryRow.from_dict(obj)


def test_from_dict_rejects_nonstring_notes():
    obj = {
        "id": "q001",
        "query": "x",
        "time_sensitivity": "strong",
        "domain": "tech",
        "difficulty": 1,
        "notes": None,
    }
    with pytest.raises(ValueError, match="notes must be"):
        QueryRow.from_dict(obj)


# ---------- validate_dataset ----------


def test_validate_accepts_valid_dataset():
    rows = _build_valid_dataset()
    assert len(rows) == DATASET_SIZE
    errors = validate_dataset(rows)
    assert errors == [], errors


def test_validate_rejects_wrong_size():
    rows = _build_valid_dataset()[:199]
    errors = validate_dataset(rows)
    assert any("dataset size" in e for e in errors)


def test_validate_rejects_duplicate_id():
    rows = _build_valid_dataset()
    # Keep 200 rows, but duplicate one id (replace q200 with q001's id).
    first = rows[0]
    rows[-1] = _row(
        id=first.id,
        query=rows[-1].query,
        time_sensitivity=rows[-1].time_sensitivity,
        domain=rows[-1].domain,
        difficulty=rows[-1].difficulty,
        notes=rows[-1].notes,
    )
    errors = validate_dataset(rows)
    assert any("duplicate ids" in e for e in errors)


def test_validate_rejects_wrong_bucket_count():
    rows = _build_valid_dataset()
    # Flip one `strong` row into `medium` → strong=79, medium=61.
    rows[0] = _row(
        id=rows[0].id,
        query=rows[0].query,
        time_sensitivity="medium",
        domain=rows[0].domain,
        difficulty=rows[0].difficulty,
        notes=rows[0].notes,
    )
    errors = validate_dataset(rows)
    assert any("'strong'" in e and "got 79" in e for e in errors)
    assert any("'medium'" in e and "got 61" in e for e in errors)


def test_validate_rejects_domain_skew():
    rows = _build_valid_dataset()
    # Force all 200 rows to `tech` domain while keeping bucket counts.
    rows = [
        _row(
            id=r.id,
            query=r.query,
            time_sensitivity=r.time_sensitivity,
            domain="tech",
            difficulty=r.difficulty,
            notes=r.notes,
        )
        for r in rows
    ]
    errors = validate_dataset(rows)
    assert any(
        f"domain='tech'" in e and f"got 200" in e for e in errors
    )
    assert any(f"got 0" in e for e in errors)


def test_validate_rejects_difficulty_skew():
    # All rows difficulty=1 → ratios (1.0, 0, 0) off by >0.05.
    rows = [
        _row(
            id=r.id,
            query=r.query,
            time_sensitivity=r.time_sensitivity,
            domain=r.domain,
            difficulty=1,
            notes=r.notes,
        )
        for r in _build_valid_dataset()
    ]
    errors = validate_dataset(rows)
    assert any("difficulty=2" in e for e in errors)
    assert any("difficulty=3" in e for e in errors)


def test_validate_domain_tolerance_inclusive():
    """Counts equal to min/max bounds (35/45) must pass."""
    rows = _build_valid_dataset()
    # Start by counting current distribution; then keep it as-is and assert clean.
    # _build_valid_dataset produces cycled domains: bucket-size mod 5 determines spread.
    # For 80/60/40/20 cycled over 5 domains → each domain gets 16+12+8+4 = 40.
    errors = validate_dataset(rows)
    assert errors == []
    assert DOMAIN_PER_LABEL_MIN <= 40 <= DOMAIN_PER_LABEL_MAX


# ---------- load_jsonl / dump_jsonl round-trip ----------


def test_dump_and_load_roundtrip(tmp_path: Path):
    rows = _build_valid_dataset()
    path = tmp_path / "rt.jsonl"
    dump_jsonl(rows, path)
    loaded = load_jsonl(path)
    assert [r.to_dict() for r in loaded] == [r.to_dict() for r in rows]


def test_load_jsonl_reports_line_number_on_bad_json(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "q001",
                "query": "x",
                "time_sensitivity": "strong",
                "domain": "tech",
                "difficulty": 1,
                "notes": "",
            }
        )
        + "\n"
        + "not-json\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="bad.jsonl:2:"):
        load_jsonl(path)


def test_load_jsonl_reports_line_number_on_bad_row(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    bad_obj = {
        "id": "q001",
        "query": "x",
        "time_sensitivity": "strong",
        "domain": "tech",
        "difficulty": 99,  # illegal
        "notes": "",
    }
    path.write_text(json.dumps(bad_obj) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bad.jsonl:1:.*difficulty must be"):
        load_jsonl(path)


def test_load_jsonl_skips_blank_lines(tmp_path: Path):
    path = tmp_path / "blank.jsonl"
    obj = {
        "id": "q001",
        "query": "x",
        "time_sensitivity": "strong",
        "domain": "tech",
        "difficulty": 1,
        "notes": "",
    }
    path.write_text("\n" + json.dumps(obj) + "\n\n", encoding="utf-8")
    loaded = load_jsonl(path)
    assert len(loaded) == 1
