"""Exit code + stderr → ErrorKind classifier.

PHASE 4 OWNER. Interface contract below is frozen — do not change signatures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ErrorKind vocabulary (matches envelope schema v1)
KIND_AUTH = "auth"
KIND_BAD_INPUT = "bad_input"
KIND_QUOTA_EXHAUSTED = "quota_exhausted"
KIND_TIMEOUT = "timeout"
KIND_CONFIG = "config"
KIND_TURN_LIMIT = "turn_limit"
KIND_MALFORMED_OUTPUT = "malformed_output"
KIND_GENERAL = "general"
KIND_TRANSIENT = "transient"  # internal signal for fallback; not surfaced in envelope


# stderr pattern tables — conservative by design (narrow positive match only).
_QUOTA_RE = re.compile(r"(quota|rate[\s_-]*limit|RESOURCE_EXHAUSTED|\b429\b)", re.IGNORECASE)
_TRANSIENT_RE = re.compile(r"(\b500\b|\b503\b|UNAVAILABLE|DEADLINE_EXCEEDED)", re.IGNORECASE)


_HINTS = {
    KIND_AUTH: "Set GEMINI_API_KEY environment variable (see README §Auth) or run `gemini auth login`.",
    KIND_BAD_INPUT: "Check CLI arguments and prompt payload — one of them was rejected as invalid.",
    KIND_CONFIG: (
        "Gemini reported a configuration error. Verify --policy path, model flag, and that "
        "no sandbox flags leaked into argv."
    ),
    KIND_TURN_LIMIT: "Increase the turn budget or shorten the task — Gemini hit its max turn limit.",
    KIND_MALFORMED_OUTPUT: (
        "Gemini exited cleanly but produced unparseable stream-json. Re-run; if reproducible, "
        "pin a known-good CLI version (see README §Compatibility)."
    ),
    KIND_TIMEOUT: "Operation exceeded the per-model timeout. Retry or narrow --target-dir scope.",
    KIND_QUOTA_EXHAUSTED: (
        "All fallback models returned quota / rate-limit errors. Wait and retry, or "
        "provide a higher-tier GEMINI_API_KEY."
    ),
    KIND_TRANSIENT: (
        "Transient upstream error (429 / 5xx). Wrapper will fall back to the next model."
    ),
    KIND_GENERAL: "Gemini failed with a non-specific error. Inspect stderr_tail for details.",
}


@dataclass
class Classification:
    kind: str           # one of the KIND_* constants above
    should_fallback: bool
    setup_hint: str


def _mk(kind: str, should_fallback: bool) -> Classification:
    return Classification(
        kind=kind,
        should_fallback=should_fallback,
        setup_hint=_HINTS.get(kind, _HINTS[KIND_GENERAL]),
    )


def classify(*, exit_code: int, stderr: str, timed_out: bool = False,
             parsed_ok: bool = True) -> Classification:
    """Classify a single attempt outcome.

    See module docstring and implementation-plan.md §5 for the full rule table.
    Conservative: when stderr is ambiguous on exit 1, we prefer KIND_GENERAL
    (no fallback) rather than wrongly retrying on a deterministic bug.
    """
    stderr = stderr or ""

    # Timeout is evaluated first: subprocess timeouts come back with exit_code == -1
    # and we should not let the stderr patterns shadow the classification.
    if timed_out:
        return _mk(KIND_TIMEOUT, should_fallback=True)

    if exit_code == 0:
        if parsed_ok:
            # Happy path; caller decides what to do. Kind is nominally general,
            # should_fallback False, so loops terminate cleanly.
            return _mk(KIND_GENERAL, should_fallback=False)
        return _mk(KIND_MALFORMED_OUTPUT, should_fallback=False)

    # Gemini CLI documented non-zero codes.
    if exit_code == 41:
        return _mk(KIND_AUTH, should_fallback=False)
    if exit_code == 42:
        return _mk(KIND_BAD_INPUT, should_fallback=False)
    if exit_code == 44:
        return _mk(KIND_CONFIG, should_fallback=False)
    if exit_code == 52:
        return _mk(KIND_CONFIG, should_fallback=False)
    if exit_code == 53:
        return _mk(KIND_TURN_LIMIT, should_fallback=False)

    if exit_code == 1:
        if _QUOTA_RE.search(stderr) or _TRANSIENT_RE.search(stderr):
            return _mk(KIND_TRANSIENT, should_fallback=True)
        return _mk(KIND_GENERAL, should_fallback=False)

    # Any other exit code: treat as general, no fallback.
    return _mk(KIND_GENERAL, should_fallback=False)
