"""Append-only JSONL audit log at ~/.cache/ask-gemini-cli/invocations.jsonl.

PHASE 7 OWNER. Interface contract below is frozen — do not change signatures.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional


LOG_SIZE_LIMIT_BYTES = 10 * 1024 * 1024   # 10 MB before rotation
LOG_DIR_MODE = 0o700
LOG_FILE_MODE = 0o600


def log_dir() -> Path:
    override = os.environ.get("ASK_GEMINI_CACHE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "ask-gemini-cli"


def log_file() -> Path:
    return log_dir() / "invocations.jsonl"


def _rotate_if_needed(path: Path) -> None:
    """Rotate `invocations.jsonl` → `invocations.1.jsonl` when size limit hit."""
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size < LOG_SIZE_LIMIT_BYTES:
        return
    rotated = path.with_name("invocations.1.jsonl")
    try:
        if rotated.exists():
            rotated.unlink()
    except OSError:
        pass
    try:
        path.rename(rotated)
    except OSError:
        pass


def append(event: dict[str, Any]) -> Optional[str]:
    """Append one event (JSON-serialized, newline-terminated) to the log.

    Rotate to `invocations.1.jsonl` when size exceeds LOG_SIZE_LIMIT_BYTES.
    Create parent dirs as needed. Never raises on I/O errors (best-effort).

    Set `ASK_GEMINI_LOG_DISABLED=1` to suppress audit logging entirely
    (returns None as a no-op so callers can't tell the difference from a
    successful write).

    Returns:
        None on success. A short human-readable reason string on failure
        (e.g. "mkdir failed", "open failed"). Callers may surface this in
        envelope.warnings so silent audit drops become visible.
    """
    if os.environ.get("ASK_GEMINI_LOG_DISABLED") == "1":
        return None
    try:
        directory = log_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return f"mkdir failed: {e.__class__.__name__}"
        try:
            os.chmod(directory, LOG_DIR_MODE)
        except OSError:
            # Tightening perms is best-effort; don't abort the append.
            pass

        path = log_file()
        _rotate_if_needed(path)

        try:
            line = json.dumps(event, ensure_ascii=False) + "\n"
        except (TypeError, ValueError):
            # Fall back to a repr-only event so we never silently lose a record.
            try:
                line = json.dumps({"event": "unserializable", "repr": repr(event)}) + "\n"
            except Exception:
                return "serialize failed"

        try:
            fd = os.open(
                str(path),
                os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                LOG_FILE_MODE,
            )
        except OSError as e:
            return f"open failed: {e.__class__.__name__}"
        try:
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as e:
            return f"write failed: {e.__class__.__name__}"
        try:
            os.chmod(path, LOG_FILE_MODE)
        except OSError:
            pass
        return None
    except Exception as e:
        # Absolute best-effort: never raise to caller.
        return f"unexpected error: {e.__class__.__name__}"
