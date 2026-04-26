"""Preflight checks: auth presence, trusted folders, auto-trust.

PHASE 6 OWNER. Interface contract below is frozen — do not change signatures.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


AUTO_TRUST_WARNING = "target dir auto-trusted for first use"
VALID_TRUST_LEVELS = ("TRUST_FOLDER", "TRUST_PARENT", "DO_NOT_TRUST")
DEFAULT_TRUST_LEVEL = "TRUST_FOLDER"
GCP_WARNING = (
    "GOOGLE_CLOUD_PROJECT is set; wrapper strips it by default "
    "(set ASK_GEMINI_KEEP_GCP=1 to keep)"
)

# Target dirs that are too broad to auto-trust. Persisting one of these into
# `~/.gemini/trustedFolders.json` would mark a system-level path as fully
# trusted across every future Gemini CLI invocation, far beyond the scope of
# a single ask-gemini call.
_DANGEROUS_TRUST_PATHS = frozenset({
    Path("/"),
    Path("/bin"),
    Path("/etc"),
    Path("/Library"),
    Path("/opt"),
    Path("/private"),
    Path("/sbin"),
    Path("/System"),
    Path("/usr"),
    Path("/usr/local"),
    Path("/var"),
})


@dataclass
class PreflightResult:
    ok: bool
    error_kind: Optional[str] = None    # 'auth' | 'config' | 'bad_input' | None
    error_message: str = ""
    setup_hint: str = ""
    warnings: list[str] = field(default_factory=list)
    auto_trusted_dirs: list[str] = field(default_factory=list)


def _gemini_home() -> Path:
    return Path.home() / ".gemini"


def _trusted_folders_file() -> Path:
    return _gemini_home() / "trustedFolders.json"


def _oauth_creds_file() -> Path:
    return _gemini_home() / "oauth_creds.json"


def _load_trusted_folders(path: Path) -> dict:
    """Load trusted folder map; return empty dict if missing/malformed."""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_trusted_folders_atomic(path: Path, data: dict) -> None:
    """Write JSON to path atomically (tmpfile + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _default_gemini_bin() -> str:
    """Resolve the default gemini binary path via lib.invoke.

    Lazy import so tests that put `lib/` on sys.path and import preflight
    directly still work (they can patch `invoke` or set GEMINI_BIN).
    """
    try:
        import invoke  # type: ignore
    except ImportError:
        from lib import invoke  # type: ignore
    return invoke.DEFAULT_GEMINI_BIN


def _check_binary() -> Optional[PreflightResult]:
    # Use invoke.gemini_bin() so preflight and build_argv agree on the
    # resolution order (env var -> $PATH -> hardcoded default). Without
    # this, preflight would fail on Linux/Intel-Mac systems before the
    # subprocess even tries to run, even though shutil.which() in
    # invoke.gemini_bin() would have found a valid binary.
    try:
        import invoke  # type: ignore
    except ImportError:
        from lib import invoke  # type: ignore
    try:
        bin_path = invoke.gemini_bin()
    except invoke.SafetyAssertionError as e:
        return PreflightResult(
            ok=False,
            error_kind="config",
            error_message=str(e),
            setup_hint=(
                "Set GEMINI_BIN to a valid path, or install Gemini CLI on "
                "$PATH (e.g., `npm i -g @google/gemini-cli`)."
            ),
        )
    p = Path(bin_path)
    if not (p.is_file() and os.access(str(p), os.X_OK)):
        return PreflightResult(
            ok=False,
            error_kind="config",
            error_message=f"Gemini binary not found or not executable at {bin_path}",
            setup_hint=(
                "Install Gemini CLI: "
                "https://geminicli.com/docs/get-started/installation "
                "or set GEMINI_BIN. The wrapper auto-detects gemini on "
                "$PATH; if your shell sees `gemini --version` working, "
                "make sure the same PATH is exported to non-interactive "
                "subprocesses."
            ),
        )
    return None


def _check_auth() -> Optional[PreflightResult]:
    if os.environ.get("GEMINI_API_KEY"):
        return None
    if _oauth_creds_file().exists():
        return None
    return PreflightResult(
        ok=False,
        error_kind="auth",
        error_message="No Gemini credentials: missing GEMINI_API_KEY and OAuth cache.",
        setup_hint=(
            "Set GEMINI_API_KEY. Get one from https://aistudio.google.com/apikey"
        ),
    )


def _check_paths(target_dir: Optional[Path],
                 artefact_file: Optional[Path],
                 image: Optional[Path],
                 pdf: Optional[Path]) -> Optional[PreflightResult]:
    checks: list[tuple[str, Optional[Path], bool]] = [
        ("target_dir", target_dir, True),   # must be a dir
        ("artefact_file", artefact_file, False),
        ("image", image, False),
        ("pdf", pdf, False),
    ]
    for label, path, must_be_dir in checks:
        if path is None:
            continue
        if not path.exists():
            return PreflightResult(
                ok=False,
                error_kind="bad_input",
                error_message=f"{label} does not exist: {path}",
                setup_hint=f"Provide a valid path for --{label.replace('_', '-')}.",
            )
        if must_be_dir and not path.is_dir():
            return PreflightResult(
                ok=False,
                error_kind="bad_input",
                error_message=f"{label} is not a directory: {path}",
                setup_hint=f"--{label.replace('_', '-')} must be a directory.",
            )
    return None


def _check_trust_target(target_dir: Path) -> Optional[PreflightResult]:
    """Reject `target_dir` values that are too broad to auto-trust.

    Auto-trust persists into `~/.gemini/trustedFolders.json` and applies to
    every subsequent Gemini CLI invocation, not just this wrapper. Marking
    `/`, `/etc`, or `$HOME` as TRUST_FOLDER permanently broadens Gemini's
    scope across the entire account, so reject those upfront.
    """
    candidates: set[Path] = set()
    # macOS symlinks `/etc` -> `/private/etc`, `/var` -> `/private/var`, etc.,
    # so `.resolve()` alone would let bare system roots slip through. Check
    # both the absolute (un-resolved) and resolved forms.
    try:
        candidates.add(target_dir.absolute())
    except OSError:
        pass
    try:
        candidates.add(target_dir.resolve())
    except OSError:
        pass
    if any(c in _DANGEROUS_TRUST_PATHS for c in candidates):
        bad = next(iter(candidates))
        return PreflightResult(
            ok=False,
            error_kind="bad_input",
            error_message=(
                f"target_dir {bad} is too broad to auto-trust"
            ),
            setup_hint=(
                "Pass a specific project subdirectory, not a system root."
            ),
        )
    resolved = next(iter(candidates), target_dir)
    try:
        if resolved == Path.home().resolve():
            return PreflightResult(
                ok=False,
                error_kind="bad_input",
                error_message=(
                    f"target_dir {resolved} ($HOME) is too broad to auto-trust"
                ),
                setup_hint=(
                    "Pass a specific project subdirectory under $HOME, not $HOME itself."
                ),
            )
    except (OSError, RuntimeError):
        pass
    return None


def _auto_trust(target_dir: Path, result: PreflightResult) -> None:
    """Ensure target_dir is in trustedFolders.json; auto-add if missing."""
    # Lazy import so tests can monkeypatch. Tests put `lib/` on sys.path
    # and patch the bare `audit_log` module, so prefer that form; fall back
    # to `lib.audit_log` in normal CLI execution.
    try:
        import audit_log  # type: ignore
    except ImportError:
        from lib import audit_log  # type: ignore

    resolved = str(target_dir.resolve())
    tf_path = _trusted_folders_file()
    trusted = _load_trusted_folders(tf_path)

    existing = trusted.get(resolved)
    if isinstance(existing, str) and existing in ("TRUST_FOLDER", "TRUST_PARENT"):
        return  # already trusted, no-op

    trusted[resolved] = DEFAULT_TRUST_LEVEL
    _write_trusted_folders_atomic(tf_path, trusted)

    result.auto_trusted_dirs.append(resolved)
    if AUTO_TRUST_WARNING not in result.warnings:
        result.warnings.append(AUTO_TRUST_WARNING)

    try:
        audit_log.append({
            "event": "auto_trusted",
            "path": resolved,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        # Audit failures must not block preflight.
        pass


def run_preflight(*, target_dir: Optional[Path] = None,
                  artefact_file: Optional[Path] = None,
                  image: Optional[Path] = None,
                  pdf: Optional[Path] = None) -> PreflightResult:
    """Verify the environment is ready to invoke gemini.

    See module docstring / implementation plan Phase 6 for ordering and
    error-kind semantics.
    """
    bin_err = _check_binary()
    if bin_err is not None:
        return bin_err

    auth_err = _check_auth()
    if auth_err is not None:
        return auth_err

    path_err = _check_paths(target_dir, artefact_file, image, pdf)
    if path_err is not None:
        return path_err

    if target_dir is not None:
        trust_err = _check_trust_target(target_dir)
        if trust_err is not None:
            return trust_err

    result = PreflightResult(ok=True)

    if target_dir is not None:
        _auto_trust(target_dir, result)

    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GOOGLE_CLOUD_PROJECT"):
        result.warnings.append(GCP_WARNING)

    return result
