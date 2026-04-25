"""`--persist-to` handling: write Gemini response to a Markdown file.

PHASE 7 OWNER. Interface contract below is frozen — do not change signatures.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


REQUIRED_SUFFIX = ".md"


def _format_stats_line(stats: Optional[dict]) -> str:
    if not isinstance(stats, dict):
        return "input=0 output=0 total=0"
    try:
        inp = int(stats.get("input_tokens", 0) or 0)
    except (TypeError, ValueError):
        inp = 0
    try:
        out = int(stats.get("output_tokens", 0) or 0)
    except (TypeError, ValueError):
        out = 0
    try:
        total = int(stats.get("total_tokens", 0) or 0)
    except (TypeError, ValueError):
        total = 0
    return f"input={inp} output={out} total={total}"


def _allowed_roots() -> list[Path]:
    """Directories under which --persist-to targets are permitted."""
    roots: list[Path] = []
    home = os.environ.get("HOME")
    if home:
        try:
            roots.append(Path(home).resolve())
        except OSError:
            pass
    try:
        roots.append(Path.cwd().resolve())
    except OSError:
        pass
    return roots


def _validate_persist_target(target: Path) -> Path:
    """Reject unsafe --persist-to targets.

    Rules (defense-in-depth; the wrapper must never let an untrusted caller
    write arbitrary files):
      * Resolved parent directory must be inside $HOME or the current working
        directory (symlink resolution is applied first).
      * Suffix must be `.md` — this is a Markdown output format, enforcing it
        prevents accidental overwrites of source files or configs.

    Returns the resolved absolute Path on success. Raises ValueError otherwise.
    Does NOT create the parent directory (that is the caller's job).
    """
    if target.suffix.lower() != REQUIRED_SUFFIX:
        raise ValueError(
            f"--persist-to target must end in {REQUIRED_SUFFIX!r}: got {target!r}"
        )

    # Resolve only-the-parent leaves a window: if `target` itself is an
    # existing symlink, the write follows it to wherever the symlink points,
    # bypassing the parent-only containment check below. Refuse upfront.
    if target.is_symlink():
        raise ValueError(
            f"--persist-to target is a symlink; refusing to follow: {target}"
        )

    try:
        parent_resolved = target.parent.resolve()
    except OSError as e:
        raise ValueError(f"cannot resolve --persist-to parent: {e}") from e

    roots = _allowed_roots()
    if not roots:
        raise ValueError(
            "neither $HOME nor current working directory is available; "
            "--persist-to is refused for safety"
        )
    for root in roots:
        try:
            if parent_resolved == root or parent_resolved.is_relative_to(root):
                return target.with_name(target.name)
        except (OSError, ValueError):
            continue

    raise ValueError(
        f"--persist-to parent {parent_resolved} is outside allowed roots "
        f"(must be under $HOME or current working directory)"
    )


def persist_response(*, target: Path, mode: str, prompt: str,
                     response: str, model_used: str,
                     stats: Optional[dict] = None) -> str:
    """Write the response to `target` as a Markdown file.

    Validates the target path (see `_validate_persist_target`) before writing.
    Raises ValueError if the target is unsafe. Otherwise returns the absolute
    path as a string. Creates parent directories as needed. Overwrites an
    existing file.
    """
    target = Path(target)
    _validate_persist_target(target)

    target.parent.mkdir(parents=True, exist_ok=True)

    generated = datetime.now(timezone.utc).isoformat()
    stats_line = _format_stats_line(stats)

    body = (
        "# ask-gemini-cli output\n"
        f"- mode: {mode}\n"
        f"- model: {model_used}\n"
        f"- generated: {generated}\n"
        f"- stats: {stats_line}\n"
        "\n"
        "## Prompt\n"
        f"{prompt}\n"
        "\n"
        "## Response\n"
        f"{response}\n"
    )

    # O_NOFOLLOW: defense-in-depth alongside the is_symlink() check in
    # _validate_persist_target. If a symlink is created at `target` between
    # validation and open(), this still refuses to follow it.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    fd = os.open(str(target), flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(body)
    return str(target.resolve())
