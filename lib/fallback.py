"""Model fallback state machine.

PHASE 4 OWNER. Interface contract below is frozen — do not change signatures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

from . import invoke as invoke_mod
from . import exit_codes as exit_codes_mod


FALLBACK_CHAIN = [
    "gemini-3-pro-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]

TIMEOUTS_S = {
    "gemini-3-pro-preview": 300,
    "gemini-2.5-pro": 180,
    "gemini-2.5-flash": 120,
}


@dataclass
class Attempt:
    model: str
    exit_code: int
    duration_ms: int


@dataclass
class ChainResult:
    success: bool
    model_used: Optional[str]
    fallback_triggered: bool
    attempts: list[Attempt] = field(default_factory=list)
    parsed: Optional[invoke_mod.ParsedOutput] = None
    final_kind: Optional[str] = None
    final_stderr_tail: str = ""
    final_exit_code: int = 0
    final_setup_hint: str = ""


_STDERR_TAIL_LINES = 40


def _tail(stderr: str, n: int = _STDERR_TAIL_LINES) -> str:
    if not stderr:
        return ""
    lines = stderr.splitlines()
    return "\n".join(lines[-n:])


def run_with_fallback(
    *,
    prompt: str,
    include_dir: Optional[Path] = None,
    runner: Callable[..., invoke_mod.InvokeResult] = invoke_mod.run,
) -> ChainResult:
    """Try each model in FALLBACK_CHAIN until one succeeds or the chain exhausts.

    `runner` is injected for test monkeypatching; it must accept keyword args
    `model`, `prompt`, `include_dir`, `timeout_s` and return an InvokeResult.
    """
    result = ChainResult(success=False, model_used=None, fallback_triggered=False)

    last_classification: Optional[exit_codes_mod.Classification] = None
    last_invoke: Optional[invoke_mod.InvokeResult] = None

    for idx, model in enumerate(FALLBACK_CHAIN):
        timeout_s = TIMEOUTS_S[model]
        invoke_result = runner(
            model=model,
            prompt=prompt,
            include_dir=include_dir,
            timeout_s=timeout_s,
        )
        last_invoke = invoke_result
        result.attempts.append(
            Attempt(
                model=model,
                exit_code=invoke_result.exit_code,
                duration_ms=invoke_result.duration_ms,
            )
        )

        parsed_ok = invoke_result.parsed is not None
        classification = exit_codes_mod.classify(
            exit_code=invoke_result.exit_code,
            stderr=invoke_result.stderr,
            timed_out=invoke_result.timed_out,
            parsed_ok=parsed_ok,
        )
        last_classification = classification

        # Success path: clean exit AND parseable output.
        if invoke_result.exit_code == 0 and parsed_ok:
            result.success = True
            result.model_used = model
            result.parsed = invoke_result.parsed
            result.fallback_triggered = len(result.attempts) > 1
            result.final_exit_code = invoke_result.exit_code
            result.final_kind = None
            result.final_stderr_tail = ""
            result.final_setup_hint = ""
            return result

        # Failure path: decide whether to keep trying.
        is_last = idx == len(FALLBACK_CHAIN) - 1
        if classification.should_fallback and not is_last:
            continue

        # Terminal failure on this attempt.
        break

    # Reached only on terminal failure (no successful return above).
    result.success = False
    result.model_used = None
    result.fallback_triggered = len(result.attempts) > 1

    if last_invoke is not None and last_classification is not None:
        # If chain exhausted while every attempt said "fallback", report it
        # as quota_exhausted per spec.
        exhausted_with_transient = (
            len(result.attempts) == len(FALLBACK_CHAIN)
            and last_classification.should_fallback
        )
        if exhausted_with_transient:
            result.final_kind = exit_codes_mod.KIND_QUOTA_EXHAUSTED
            result.final_setup_hint = exit_codes_mod._HINTS[exit_codes_mod.KIND_QUOTA_EXHAUSTED]
        else:
            result.final_kind = last_classification.kind
            result.final_setup_hint = last_classification.setup_hint
        result.final_exit_code = last_invoke.exit_code
        result.final_stderr_tail = _tail(last_invoke.stderr)

    return result
