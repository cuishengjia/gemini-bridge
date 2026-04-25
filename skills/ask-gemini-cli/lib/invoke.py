"""Build argv for `gemini`, spawn subprocess, parse stream-json output.

Safety invariants enforced here:
  * --approval-mode plan         (hardcoded, not overridable via wrapper CLI)
  * -o stream-json                (hardcoded; we parse events internally)
  * --policy <SKILL_DIR>/policies/readonly.toml (hardcoded)

`build_argv()` is a pure function and is the primary unit-test surface.
`run()` spawns the subprocess and returns an InvokeResult for fallback.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_GEMINI_BIN = "/opt/homebrew/bin/gemini"
POLICY_RELATIVE = "policies/readonly.toml"

# World-writable / temp-style locations: a `gemini` binary placed here is
# almost always either a misconfiguration or a local-privesc attempt. Refuse
# to spawn unless the user explicitly opts out with ASK_GEMINI_BIN_UNRESTRICTED=1.
_DANGEROUS_BIN_PREFIXES = (
    Path("/tmp"),
    Path("/var/tmp"),
    Path("/dev/shm"),
    Path("/private/tmp"),
    Path("/private/var/tmp"),
)

# Event types that carry the model's internal chain-of-thought / planning
# tokens. These MUST NOT be merged into `response`:
#   * `gemini-3-pro-preview` (2025-11+) emits `type="thought"` events whose
#     `content` is raw CoT ("Wait, let me search...", "CRITICAL INSTRUCTION:
#     ...", plus internal tool-list enumerations). Before this filter, the
#     catch-all "non-message + no role" fallback in `_parse_events` was
#     concatenating these straight into the final answer (see q082 incident
#     in `/tmp/q082_diagnosis.md`).
#   * The second-opinion mode is specifically neutered by CoT leakage: its
#     whole value is an *independent* review, which is destroyed if the
#     Gemini model's reasoning is surfaced to Claude.
# We accept that future unknown event types default to ignored rather than
# default to included — CoT-style payloads are the most likely novel stream.
THOUGHT_EVENT_TYPES = {
    "thought",
    "thinking",
    "reasoning",
    "reflection",
    "scratchpad",
}

# Event types that are safe fallbacks for content/delta aggregation even
# when `role` is absent. Any `type` outside this set (and outside `message`,
# which has its own role-gated path) is ignored by the content aggregator.
CONTENT_FALLBACK_TYPES = {None, "response_chunk", "delta"}


@dataclass
class ParsedOutput:
    response: str
    stats: dict
    tool_calls: list[dict]
    # Count of stream-json events whose `type` matched THOUGHT_EVENT_TYPES and
    # were dropped before content aggregation. Surfaced via envelope warnings
    # as `model_emitted_thought_events` so callers know the model tried to
    # emit chain-of-thought even though we filtered it out.
    thought_events_dropped: int = 0


@dataclass
class InvokeResult:
    exit_code: int
    duration_ms: int
    stderr: str
    raw_events: list[dict]
    parsed: Optional[ParsedOutput]
    timed_out: bool = False


class SafetyAssertionError(RuntimeError):
    """Raised if a caller tries to break an invariant."""


def skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def policy_path() -> Path:
    return skill_dir() / POLICY_RELATIVE


def gemini_bin() -> str:
    raw = os.environ.get("GEMINI_BIN", DEFAULT_GEMINI_BIN)
    if os.environ.get("ASK_GEMINI_BIN_UNRESTRICTED") == "1":
        return raw
    return _validate_bin_path(raw)


def _validate_bin_path(bin_path: str) -> str:
    """Reject GEMINI_BIN values pointing at world-writable temp locations.

    Existence / executability is checked separately by preflight._check_binary;
    here we only screen the *path* so that an attacker who can plant a binary
    in /tmp cannot persuade the wrapper to run it. Set
    ASK_GEMINI_BIN_UNRESTRICTED=1 to bypass for legitimate edge cases.
    """
    if not bin_path:
        raise SafetyAssertionError("GEMINI_BIN must not be empty")
    p = Path(bin_path)
    try:
        candidate = p.resolve(strict=False)
    except OSError as e:
        raise SafetyAssertionError(f"GEMINI_BIN cannot be resolved: {e}") from e
    for danger in _DANGEROUS_BIN_PREFIXES:
        try:
            if candidate == danger or candidate.is_relative_to(danger):
                raise SafetyAssertionError(
                    f"GEMINI_BIN points to a world-writable location "
                    f"({candidate}); refusing to spawn. Set "
                    f"ASK_GEMINI_BIN_UNRESTRICTED=1 to override."
                )
        except ValueError:
            continue
    return bin_path


def build_argv(
    *,
    model: str,
    prompt: str,
    include_dir: Optional[Path] = None,
    extra_env: Optional[dict] = None,
) -> list[str]:
    """Return the argv for a single gemini invocation.

    Safety invariants are enforced here (and re-asserted below for defense
    in depth).
    """
    if not model or not isinstance(model, str):
        raise SafetyAssertionError(f"model must be a non-empty string, got {model!r}")
    if prompt is None:
        raise SafetyAssertionError("prompt must not be None")

    argv: list[str] = [
        gemini_bin(),
        "--approval-mode", "plan",
        "-m", model,
        "-o", "stream-json",
        "--policy", str(policy_path()),
    ]
    if include_dir is not None:
        dir_str = str(include_dir)
        if dir_str.startswith("-"):
            raise SafetyAssertionError(
                f"include_dir must not start with '-' (argv injection guard): {dir_str!r}"
            )
        argv += ["--include-directories", dir_str]
    argv += ["-p", prompt]

    _assert_safety(argv)
    return argv


def _assert_safety(argv: list[str]) -> None:
    """Defense-in-depth: re-check invariants right before spawning."""
    joined = argv
    if "--approval-mode" not in joined:
        raise SafetyAssertionError("missing --approval-mode flag")
    idx = joined.index("--approval-mode")
    if idx + 1 >= len(joined) or joined[idx + 1] != "plan":
        raise SafetyAssertionError("--approval-mode must be 'plan'")

    if "-o" not in joined:
        raise SafetyAssertionError("missing -o flag")
    idx = joined.index("-o")
    if idx + 1 >= len(joined) or joined[idx + 1] != "stream-json":
        raise SafetyAssertionError("-o must be 'stream-json'")

    if "--policy" not in joined:
        raise SafetyAssertionError("missing --policy flag")

    forbidden = {
        "-s", "--sandbox",
        "--yolo",
        "--approval-mode=auto",
        "--approval-mode=auto_edit",
        "--approval-mode=yolo",
        "--approval-mode=default",
        "--admin-policy",
        "--allowed-tools",
    }
    for token in argv:
        if token in forbidden:
            raise SafetyAssertionError(f"forbidden flag present: {token}")


def _prepare_env() -> dict:
    """Return an env dict for the subprocess.

    - Pass through GEMINI_API_KEY (preferred auth).
    - Strip GOOGLE_CLOUD_PROJECT by default (org-subscription checks can hang);
      user can opt-in by setting ASK_GEMINI_KEEP_GCP=1.
    """
    env = os.environ.copy()
    if env.get("ASK_GEMINI_KEEP_GCP") != "1":
        env.pop("GOOGLE_CLOUD_PROJECT", None)
    return env


def _parse_events(raw_lines: list[str]) -> tuple[list[dict], Optional[ParsedOutput]]:
    """Parse stream-json JSONL output into events + final ParsedOutput.

    The stream-json event schema from Gemini CLI is not fully contract-stable
    across versions, so we parse defensively:
      - Any line that parses as JSON is an event.
      - Tool-call events: recognized by `type == "tool_use"` or presence of a
        `name` field alongside tool-shaped input (query/url/path).
      - Final response: last event containing a text `response` field, OR
        concatenation of `content`/`delta` fields if split across events.
      - Stats: last event with `stats` or `usage`.
    """
    events: list[dict] = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):
            events.append(ev)

    if not events:
        return events, None

    # Drop thought/reasoning events before any downstream aggregation.
    # We keep them out of `events` entirely rather than skipping per-branch
    # because (a) their content/delta/text could be picked up by multiple
    # paths and (b) the envelope has no need to expose them — the caller is
    # Claude, which does its own reasoning.
    thought_count = sum(1 for ev in events if ev.get("type") in THOUGHT_EVENT_TYPES)
    events = [ev for ev in events if ev.get("type") not in THOUGHT_EVENT_TYPES]
    if not events:
        return events, None

    tool_calls: list[dict] = []
    for ev in events:
        if ev.get("type") == "tool_use" or (
            "name" in ev and any(k in ev for k in ("input", "query", "url", "path"))
        ):
            call = {"name": ev.get("name") or ev.get("tool_name") or "unknown"}
            if "query" in ev:
                call["query"] = ev["query"]
            elif isinstance(ev.get("input"), dict) and "query" in ev["input"]:
                call["query"] = ev["input"]["query"]
            if "url" in ev:
                call["url"] = ev["url"]
            tool_calls.append(call)

    # Gemini CLI emits `type=message` events for BOTH the user-side prompt
    # echo (`role=user`) and the assistant's reply (`role=assistant` or
    # `role=model`). Only assistant/model content contributes to `response`;
    # untyped text/response fields still flow through for forward-compatibility.
    assistant_roles = {"assistant", "model"}
    response_text = ""
    stats: dict = {}
    content_chunks: list[str] = []
    for ev in events:
        role = ev.get("role")
        ev_type = ev.get("type")
        is_assistant_msg = (ev_type == "message" and role in assistant_roles)
        # Whitelist the types that may contribute to `response` when role is
        # absent. Anything outside this set (e.g. future `debug`, `trace`,
        # `plan`, or unknown CoT-adjacent events) is silently dropped rather
        # than default-included. This replaces the old `type != "message"`
        # blacklist, which defaulted to inclusion and leaked CoT into q082.
        is_content_fallback = (
            ev_type in CONTENT_FALLBACK_TYPES and role is None
        )

        if isinstance(ev.get("response"), str):
            response_text = ev["response"]
        elif isinstance(ev.get("text"), str) and ev_type in ("response", "final"):
            response_text = ev["text"]
        elif isinstance(ev.get("text"), str) and is_assistant_msg:
            response_text = ev["text"]

        if isinstance(ev.get("content"), str) and (is_assistant_msg or is_content_fallback):
            content_chunks.append(ev["content"])
        elif isinstance(ev.get("delta"), str) and (is_assistant_msg or is_content_fallback):
            content_chunks.append(ev["delta"])

        if isinstance(ev.get("stats"), dict):
            stats = ev["stats"]
        elif isinstance(ev.get("usage"), dict):
            stats = ev["usage"]

    if not response_text and content_chunks:
        response_text = "".join(content_chunks)

    if not response_text:
        return events, None

    norm_stats = {
        "input_tokens": int(stats.get("input_tokens", stats.get("prompt_tokens", 0)) or 0),
        "output_tokens": int(stats.get("output_tokens", stats.get("completion_tokens", 0)) or 0),
        "cached_tokens": int(stats.get("cached_tokens", stats.get("cache_read_tokens", 0)) or 0),
        "total_tokens": int(stats.get("total_tokens", 0) or 0),
    }
    if norm_stats["total_tokens"] == 0:
        norm_stats["total_tokens"] = (
            norm_stats["input_tokens"]
            + norm_stats["output_tokens"]
            + norm_stats["cached_tokens"]
        )

    return events, ParsedOutput(
        response=response_text,
        stats=norm_stats,
        tool_calls=tool_calls,
        thought_events_dropped=thought_count,
    )


def run(
    *,
    model: str,
    prompt: str,
    timeout_s: int,
    include_dir: Optional[Path] = None,
) -> InvokeResult:
    """Spawn gemini, collect stream-json output, classify result."""
    argv = build_argv(model=model, prompt=prompt, include_dir=include_dir)
    env = _prepare_env()

    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            argv,
            input="",
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        stdout = proc.stdout
        stderr = proc.stderr
        exit_code = proc.returncode
    except subprocess.TimeoutExpired as e:
        timed_out = True
        stdout = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        exit_code = -1
    duration_ms = int((time.monotonic() - start) * 1000)

    raw_lines = (stdout or "").splitlines()
    events, parsed = _parse_events(raw_lines)

    return InvokeResult(
        exit_code=exit_code,
        duration_ms=duration_ms,
        stderr=stderr or "",
        raw_events=events,
        parsed=parsed,
        timed_out=timed_out,
    )
