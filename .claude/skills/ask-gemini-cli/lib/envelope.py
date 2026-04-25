"""Envelope builders + JSON schema (frozen v1).

PHASE 7 OWNER. Interface contract below is frozen — do not change signatures.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Optional

from . import fallback as fb_mod


ENVELOPE_VERSION = 1

_STATS_FIELDS = ("input_tokens", "output_tokens", "cached_tokens", "total_tokens")


def _attempt_to_dict(a: Any) -> dict:
    """Coerce an Attempt-like object (dataclass or dict) to a safe dict."""
    if a is None:
        return {"model": "", "exit_code": 0, "duration_ms": 0}
    if is_dataclass(a) and not isinstance(a, type):
        try:
            d = asdict(a)
        except Exception:
            d = {}
    elif isinstance(a, dict):
        d = dict(a)
    else:
        d = {
            "model": getattr(a, "model", ""),
            "exit_code": getattr(a, "exit_code", 0),
            "duration_ms": getattr(a, "duration_ms", 0),
        }
    return {
        "model": str(d.get("model", "") or ""),
        "exit_code": int(d.get("exit_code", 0) or 0),
        "duration_ms": int(d.get("duration_ms", 0) or 0),
    }


def _normalize_stats(raw: Any) -> dict:
    """Always return a dict with all four int stat fields present."""
    if not isinstance(raw, dict):
        raw = {}
    out: dict[str, int] = {}
    for key in _STATS_FIELDS:
        try:
            out[key] = int(raw.get(key, 0) or 0)
        except (TypeError, ValueError):
            out[key] = 0
    return out


def _normalize_tool_calls(raw: Any) -> list[dict]:
    """Return a list of dicts; skip non-dict items defensively."""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def build_success(
    *,
    mode: str,
    chain_result: fb_mod.ChainResult,
    persisted_to: Optional[str] = None,
    warnings: Optional[list[str]] = None,
) -> dict:
    """Build a success envelope (ok=True). Never raises."""
    attempts_raw = getattr(chain_result, "attempts", None) or []
    attempts = [_attempt_to_dict(a) for a in attempts_raw]

    parsed = getattr(chain_result, "parsed", None)
    if parsed is not None:
        response = getattr(parsed, "response", "") or ""
        stats = _normalize_stats(getattr(parsed, "stats", None))
        tool_calls = _normalize_tool_calls(getattr(parsed, "tool_calls", None))
    else:
        response = ""
        stats = _normalize_stats(None)
        tool_calls = []

    model_used = getattr(chain_result, "model_used", None) or ""
    fallback_triggered = bool(getattr(chain_result, "fallback_triggered", False))

    warn_list: list[str] = []
    if isinstance(warnings, list):
        warn_list = [str(w) for w in warnings if w is not None]

    persisted_val: Optional[str]
    if persisted_to is None:
        persisted_val = None
    else:
        persisted_val = str(persisted_to)

    return {
        "ok": True,
        "mode": str(mode),
        "model_used": str(model_used),
        "fallback_triggered": fallback_triggered,
        "attempts": attempts,
        "response": str(response),
        "stats": stats,
        "tool_calls": tool_calls,
        "persisted_to": persisted_val,
        "warnings": warn_list,
    }


def build_error(
    *,
    mode: str,
    kind: str,
    message: str,
    setup_hint: str = "",
    exit_code: int = 0,
    stderr_tail: str = "",
    attempts: Optional[list[fb_mod.Attempt]] = None,
) -> dict:
    """Build an error envelope (ok=False). Never raises."""
    if attempts is None:
        attempts_out: list[dict] = []
    elif isinstance(attempts, list):
        attempts_out = [_attempt_to_dict(a) for a in attempts]
    else:
        attempts_out = []

    try:
        ec = int(exit_code)
    except (TypeError, ValueError):
        ec = 0

    return {
        "ok": False,
        "mode": str(mode),
        "error": {
            "kind": str(kind or "general"),
            "message": str(message or ""),
            "setup_hint": str(setup_hint or ""),
            "exit_code": ec,
            "stderr_tail": str(stderr_tail or ""),
        },
        "attempts": attempts_out,
    }


def tail_lines(text: str, n: int = 40) -> str:
    """Return last n lines of text. Utility used by build_error."""
    if not text:
        return ""
    lines = text.splitlines()
    if n <= 0:
        return ""
    return "\n".join(lines[-n:])
