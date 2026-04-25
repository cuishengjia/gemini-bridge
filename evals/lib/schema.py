"""Dataset schema and validation for the research-mode eval framework.

Locks the `research_200.jsonl` row shape as an immutable dataclass and
provides a `validate_dataset` function that enforces every invariant
recorded in `evals/README.md` (row count, bucket ratios, domain spread,
difficulty distribution, id uniqueness, enum legality).

All functions are pure and side-effect free.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

TIME_SENSITIVITY_VALUES: frozenset[str] = frozenset(
    {"strong", "medium", "evergreen_obscure", "evergreen_common"}
)
DOMAIN_VALUES: frozenset[str] = frozenset(
    {"tech", "news_finance", "science", "lifestyle", "sports_people"}
)
DIFFICULTY_VALUES: frozenset[int] = frozenset({1, 2, 3})

# Locked bucket counts for the 200-row dataset. See evals/README.md §Dataset.
BUCKET_COUNTS: dict[str, int] = {
    "strong": 80,
    "medium": 60,
    "evergreen_obscure": 40,
    "evergreen_common": 20,
}
DATASET_SIZE: int = sum(BUCKET_COUNTS.values())  # 200

# Tolerance windows (inclusive). See planner decisions locked in README.
DOMAIN_PER_LABEL_MIN: int = 35
DOMAIN_PER_LABEL_MAX: int = 45

DIFFICULTY_TARGETS: dict[int, float] = {1: 0.60, 2: 0.30, 3: 0.10}
DIFFICULTY_TOLERANCE: float = 0.05  # +/- 5 percentage points


@dataclass(frozen=True)
class QueryRow:
    """One line of `research_200.jsonl`, immutable after construction."""

    id: str
    query: str
    time_sensitivity: str
    domain: str
    difficulty: int
    notes: str

    @classmethod
    def from_dict(cls, obj: dict) -> "QueryRow":
        """Build a QueryRow from a decoded JSON object.

        Only performs structural typing and enum checks; does not enforce
        dataset-level invariants (that is `validate_dataset`'s job).
        """
        required = {"id", "query", "time_sensitivity", "domain", "difficulty", "notes"}
        missing = required - obj.keys()
        if missing:
            raise ValueError(f"missing required keys: {sorted(missing)}")
        extra = obj.keys() - required
        if extra:
            raise ValueError(f"unexpected keys: {sorted(extra)}")

        if not isinstance(obj["id"], str) or not obj["id"]:
            raise ValueError("id must be a non-empty string")
        if not isinstance(obj["query"], str) or not obj["query"].strip():
            raise ValueError("query must be a non-empty string")
        if obj["time_sensitivity"] not in TIME_SENSITIVITY_VALUES:
            raise ValueError(
                f"time_sensitivity must be one of {sorted(TIME_SENSITIVITY_VALUES)}, "
                f"got {obj['time_sensitivity']!r}"
            )
        if obj["domain"] not in DOMAIN_VALUES:
            raise ValueError(
                f"domain must be one of {sorted(DOMAIN_VALUES)}, got {obj['domain']!r}"
            )
        if obj["difficulty"] not in DIFFICULTY_VALUES:
            raise ValueError(
                f"difficulty must be one of {sorted(DIFFICULTY_VALUES)}, "
                f"got {obj['difficulty']!r}"
            )
        if not isinstance(obj["notes"], str):
            raise ValueError("notes must be a string (empty allowed)")

        return cls(
            id=obj["id"],
            query=obj["query"],
            time_sensitivity=obj["time_sensitivity"],
            domain=obj["domain"],
            difficulty=obj["difficulty"],
            notes=obj["notes"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "query": self.query,
            "time_sensitivity": self.time_sensitivity,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "notes": self.notes,
        }


def validate_dataset(rows: Sequence[QueryRow]) -> list[str]:
    """Enforce locked dataset invariants. Returns a list of error messages.

    An empty list means the dataset passes all checks.
    """
    errors: list[str] = []

    if len(rows) != DATASET_SIZE:
        errors.append(f"dataset size must be {DATASET_SIZE}, got {len(rows)}")

    ids = [r.id for r in rows]
    id_counts = Counter(ids)
    duplicates = sorted(i for i, c in id_counts.items() if c > 1)
    if duplicates:
        errors.append(f"duplicate ids: {duplicates}")

    bucket_counts = Counter(r.time_sensitivity for r in rows)
    for bucket, expected in BUCKET_COUNTS.items():
        actual = bucket_counts.get(bucket, 0)
        if actual != expected:
            errors.append(
                f"time_sensitivity={bucket!r}: expected {expected}, got {actual}"
            )

    illegal_buckets = set(bucket_counts) - TIME_SENSITIVITY_VALUES
    if illegal_buckets:
        errors.append(
            f"illegal time_sensitivity values: {sorted(illegal_buckets)}"
        )

    domain_counts = Counter(r.domain for r in rows)
    illegal_domains = set(domain_counts) - DOMAIN_VALUES
    if illegal_domains:
        errors.append(f"illegal domain values: {sorted(illegal_domains)}")
    for domain in DOMAIN_VALUES:
        count = domain_counts.get(domain, 0)
        if not (DOMAIN_PER_LABEL_MIN <= count <= DOMAIN_PER_LABEL_MAX):
            errors.append(
                f"domain={domain!r}: expected "
                f"[{DOMAIN_PER_LABEL_MIN}, {DOMAIN_PER_LABEL_MAX}], got {count}"
            )

    difficulty_counts = Counter(r.difficulty for r in rows)
    illegal_diff = set(difficulty_counts) - DIFFICULTY_VALUES
    if illegal_diff:
        errors.append(f"illegal difficulty values: {sorted(illegal_diff)}")
    total = len(rows) or 1
    for level, target in DIFFICULTY_TARGETS.items():
        ratio = difficulty_counts.get(level, 0) / total
        if abs(ratio - target) > DIFFICULTY_TOLERANCE:
            errors.append(
                f"difficulty={level}: expected ratio {target:.2f} "
                f"+/- {DIFFICULTY_TOLERANCE}, got {ratio:.3f}"
            )

    return errors


def load_jsonl(path: Path) -> list[QueryRow]:
    """Load a `research_200.jsonl`-shaped file into QueryRow objects.

    Raises ValueError with a line number on the first malformed row so the
    caller can point at the offending entry directly.
    """
    rows: list[QueryRow] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {e}") from e
            try:
                rows.append(QueryRow.from_dict(obj))
            except ValueError as e:
                raise ValueError(f"{path}:{lineno}: {e}") from e
    return rows


def dump_jsonl(rows: Iterable[QueryRow], path: Path) -> None:
    """Write rows to JSONL, one compact object per line (stable key order)."""
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row.to_dict(), ensure_ascii=False))
            fh.write("\n")
