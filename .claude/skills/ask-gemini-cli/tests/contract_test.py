"""Contract test: validate real envelopes against docs/envelope-schema.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

jsonschema = pytest.importorskip("jsonschema",
                                 reason="jsonschema not installed")

from lib import envelope  # noqa: E402
from lib.fallback import Attempt, ChainResult  # noqa: E402
from lib.invoke import ParsedOutput  # noqa: E402


SCHEMA_PATH = SKILL_DIR / "docs" / "envelope-schema.json"


def _load_schema() -> dict:
    with SCHEMA_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _build_sample_success_envelope() -> dict:
    parsed = ParsedOutput(
        response="sample response",
        stats={
            "input_tokens": 1200, "output_tokens": 400,
            "cached_tokens": 0, "total_tokens": 1600,
        },
        tool_calls=[{"name": "google_web_search", "query": "hello world"}],
    )
    chain = ChainResult(
        success=True,
        model_used="gemini-3-pro-preview",
        fallback_triggered=False,
        attempts=[Attempt(model="gemini-3-pro-preview", exit_code=0, duration_ms=1234)],
        parsed=parsed,
    )
    return envelope.build_success(
        mode="research",
        chain_result=chain,
        persisted_to="/tmp/sample.md",
        warnings=["target dir auto-trusted for first use"],
    )


def _build_sample_error_envelope() -> dict:
    return envelope.build_error(
        mode="analyze",
        kind="quota_exhausted",
        message="all models exhausted",
        setup_hint="Wait for quota reset or switch API key.",
        exit_code=1,
        stderr_tail="429 RESOURCE_EXHAUSTED",
        attempts=[
            Attempt(model="gemini-3-pro-preview", exit_code=1, duration_ms=100),
            Attempt(model="gemini-2.5-pro", exit_code=1, duration_ms=120),
            Attempt(model="gemini-2.5-flash", exit_code=1, duration_ms=140),
        ],
    )


def test_schema_file_is_valid_json() -> None:
    schema = _load_schema()
    assert "$schema" in schema
    assert schema.get("title", "").startswith("ask-gemini-cli envelope")


def test_success_envelope_validates_against_schema() -> None:
    schema = _load_schema()
    env = _build_sample_success_envelope()
    jsonschema.validate(instance=env, schema=schema)


def test_error_envelope_validates_against_schema() -> None:
    schema = _load_schema()
    env = _build_sample_error_envelope()
    jsonschema.validate(instance=env, schema=schema)


def test_invalid_envelope_rejected() -> None:
    schema = _load_schema()
    bad = {"ok": True, "mode": "analyze"}  # missing required success fields
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)
