---
name: ask-gemini-cli
description: >
  Delegate an analytical task to Google's Gemini CLI when Claude Code needs
  capabilities beyond its own: (1) large-context codebase analysis over a 1M+
  token window, (2) Google-search-grounded research with live URL citations
  for time-sensitive or post-training-cutoff facts, (3) a blind independent
  second opinion on a plan, design, or patch from a different model lineage,
  or (4) multimodal analysis of images, PDFs, or video frames. Gemini runs
  strictly read-only (approval-mode=plan + policy whitelist) and cannot edit
  files or run shell commands. Invoke this skill when the task is analytical
  and Claude needs more context, fresh web information, an independent critic,
  or visual understanding — not for file edits or code execution.
---

# ask-gemini-cli

A read-only bridge from Claude Code to the `gemini` CLI. Four modes, one wrapper,
one structured envelope.

## When to invoke

Pick this skill when ANY of the following is true:

- The target is **too large for Claude's context** (whole monorepo, large log
  dump, multi-hundred-file codebase) → `--mode analyze`.
- The question requires **fresh web information** (current versions, recent
  incidents, post-cutoff news, library changelog lookups) → `--mode research`.
- The user wants a **second opinion** on a design, plan, review, or patch,
  and it matters that the critic is **independent** (different model lineage,
  no access to Claude's reasoning chain) → `--mode second-opinion`.
- The input is **non-text** (screenshot, UI mockup, PDF, video frame) and
  needs to be analyzed → `--mode multimodal`.

Do NOT invoke when:
- The task requires writing files or running shell (Gemini is read-only here).
- The task is small enough for Claude to do directly — this skill costs a
  subprocess, a network round-trip, and Gemini quota.
- Secrecy is required — Gemini sees the prompt, target files, and (if used)
  the artefact.

## Invocation

The wrapper lives at `bin/ask-gemini` inside this skill directory. All four
modes return the same JSON envelope schema (see §Envelope below).

### Mode 1: analyze — large-context codebase analysis

```bash
bin/ask-gemini \
  --mode analyze \
  --target-dir <absolute_path> \
  --prompt "<what to analyze>" \
  [--persist-to <path.md>]
```

Gemini reads files under `<target-dir>` via `read_file` / `glob` / `grep`
tools (allowed by the policy). Use when Claude cannot fit the relevant code
into context.

### Mode 2: research — Google-grounded web research

```bash
bin/ask-gemini \
  --mode research \
  --query "<question>" \
  [--target-dir <absolute_path>] \
  [--persist-to <path.md>]
```

Gemini is instructed to use `google_web_search` and `web_fetch`. The envelope
`tool_calls` field will show which queries fired and which URLs were fetched.
Prefer this over letting Claude guess from training data for anything where
freshness matters.

### Mode 3: second-opinion — blind independent critique

```bash
bin/ask-gemini \
  --mode second-opinion \
  --task "<what problem is being solved>" \
  --artefact-file <path_to_plan_or_patch> \
  [--persist-to <path.md>]
```

**CRITICAL — blind review invariant**: `--task` must describe the problem
being solved, NOT Claude's reasoning, conclusions, or recommended solution.
The entire point is to get an independent verdict. Leaking Claude's
reasoning chain defeats the mode.

- ✅ Good `--task`: "Users report that pagination skips items when the
  dataset shrinks between requests; we need to decide how to stabilize it."
- ❌ Bad `--task`: "I concluded we should use cursor pagination with a
  snapshot; please agree."

### Mode 4: multimodal — images, PDFs, video frames

```bash
bin/ask-gemini \
  --mode multimodal \
  --image <path> | --pdf <path> \
  --prompt "<what to analyze>" \
  [--persist-to <path.md>]
```

The wrapper passes the media to Gemini by embedding `@<absolute_path>` inside
the rendered prompt (Gemini's standard file-reference syntax) and injecting
the media's parent directory as `--include-directories` so the policy can
reach the file. The caller only supplies a regular filesystem path.

## Claude-side rules (important)

1. **Never override approval mode.** The wrapper hardcodes
   `--approval-mode plan` and a read-only policy. Do not pass flags that
   attempt to change this.
2. **Never leak Claude's reasoning chain into `--task`** for
   `second-opinion`. See Mode 3 above.
3. **Treat the envelope as authoritative.** Check `ok` first, then branch
   on `error.kind` for failures (see Envelope §error kinds below).
4. **`--persist-to` is for cross-session reuse.** When Gemini's output is
   worth keeping (e.g., a map of a large codebase, a research summary),
   pass `--persist-to docs/gemini-notes/<topic>.md` so a later session can
   read the file directly instead of re-running the query. The path **must**
   (a) end in `.md` / `.MD` (case-insensitive) and (b) resolve under `$HOME`
   or the current working directory. Paths outside both roots are rejected
   before any file is written, so Gemini cannot be used to clobber system
   files. Existing `.md` targets are overwritten.
5. **Cost awareness.** Each call consumes Gemini quota. The envelope
   returns `stats.total_tokens`; surface this to the user if a call is
   unexpectedly large.

## Envelope

Every invocation prints a single JSON object to stdout. Schema v1 (frozen):

### Success

```json
{
  "ok": true,
  "mode": "analyze | research | second-opinion | multimodal",
  "model_used": "gemini-3-pro-preview",
  "fallback_triggered": false,
  "attempts": [{"model": "...", "exit_code": 0, "duration_ms": 14200}],
  "response": "<Gemini's .response text verbatim>",
  "stats": {
    "input_tokens": 0, "output_tokens": 0,
    "cached_tokens": 0, "total_tokens": 0
  },
  "tool_calls": [{"name": "google_web_search", "query": "..."}],
  "persisted_to": "/path/to/file.md",
  "warnings": []
}
```

### Failure

```json
{
  "ok": false,
  "mode": "...",
  "error": {
    "kind": "auth | bad_input | quota_exhausted | timeout | config | turn_limit | malformed_output | general",
    "message": "<one-line human summary>",
    "setup_hint": "<what to do next>",
    "exit_code": 41,
    "stderr_tail": "<last 40 lines of gemini stderr>"
  },
  "attempts": [...]
}
```

### Warnings (success-path signals)

The `warnings[]` array on a success envelope is a non-fatal quality channel.
`ok=true` is not revoked when warnings fire; Claude should surface them to
the user if they affect answer trust. Known warning strings:

| `warnings[]` entry | Meaning | Claude should |
|---|---|---|
| `model_emitted_thought_events` | Gemini (typically `gemini-3-pro-preview`) streamed `type=thought` / `thinking` / `reasoning` events which the wrapper filtered out before assembling `response`. No CoT leaked into the output, but the model tried. | Trust the `response` field — the filter is known-good (203 regression tests, 94% coverage). Optionally note in summaries that the underlying model emitted CoT. |
| `zero_url_response` | `research` mode returned a body with no `http://` or `https://` URL. Almost always means the prompt's citation contract was ignored. | Treat the research answer with reduced trust. If freshness / citation accuracy matters, re-run with a tighter `--query` or fall back to training-data answer with explicit caveat. |
| `auto_trusted` | Preflight auto-added `<target-dir>` to `~/.config/gemini/trustedFolders.json`. | Inform the user the folder was marked trusted; no action needed unless they want it revoked. |
| `audit log write skipped: <reason>` | Local invocation log could not be written (disk full / permission). | Non-blocking; mention if debugging repeat failures. |

New warning strings may be added over time; callers should treat unknown
entries as informational rather than fatal.

### Error kinds and how to react

| `error.kind` | What it means | What Claude should do |
|---|---|---|
| `auth` | `GEMINI_API_KEY` missing or rejected | Ask user to set it; do NOT retry automatically |
| `bad_input` | Malformed CLI args from our wrapper | Treat as a wrapper bug; report to user |
| `quota_exhausted` | All fallback models returned quota errors | Tell user; suggest waiting or a smaller scope |
| `timeout` | Gemini did not finish within the model's timeout | Retry with smaller scope or narrower prompt |
| `config` | Trusted-folder / policy / settings misconfigured | Follow `setup_hint` exactly |
| `turn_limit` | Agent hit internal step cap | Narrow the task |
| `malformed_output` | Gemini returned non-JSON or missing fields | Report to user; likely a CLI version change |
| `general` | Uncategorized exit 1 | Show `stderr_tail` to user |

## Model fallback chain (wrapper-managed)

```
gemini-3-pro-preview  →  gemini-2.5-pro  →  gemini-2.5-flash
```

`flash-lite` is deliberately excluded (analytical quality too low; better to
surface quota exhaustion than to silently degrade). Fallback triggers only
on quota / transient errors — never on auth, bad input, or config errors.

## Logs

Every invocation is appended to `~/.cache/ask-gemini-cli/invocations.jsonl`
(10 MB rotating) — one envelope per line, plus preflight audit events
(e.g. `auto_trusted`). Useful for debugging and for retrospective cost
accounting.

## See also

- `README.md` — setup (auth, `.geminiignore`, troubleshooting)
- `MIGRATION.md` — how to promote the skill from project-local to user-global
- `docs/implementation-plan.md` — frozen design decisions
