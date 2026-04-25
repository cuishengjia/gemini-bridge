---
name: analyze
description: Delegate large-context codebase analysis to Google's Gemini CLI when the target is too big for Claude's own context window — entire monorepos, hundreds of files, large log dumps. Gemini reads files via read_file/glob/grep tools (allowed by a read-only policy) over a 1M+ token window and returns a single JSON envelope. Invoke when the user asks Claude to "analyze this whole project / repo / codebase / log dump" and the scope is clearly beyond what Claude can fit in its own context. Do NOT invoke for small files Claude can read directly, for tasks requiring file edits (Gemini is read-only here), or when secrecy matters (Gemini sees the prompt and target files).
---

# gemini-bridge:analyze

Read-only codebase analysis powered by Google Gemini CLI's 1M+ token window.

## When to use

- User says "analyze this repo / project / monorepo"
- The target spans many files / large size that won't fit Claude's context
- User wants a high-level architectural map, code review, or dependency analysis on a sizable codebase
- Log dumps, large CSVs, or any file too big for Claude to read directly

## Invocation

```bash
"$CLAUDE_PLUGIN_ROOT/bin/ask-gemini" \
  --mode analyze \
  --target-dir "<absolute path to project root>" \
  --prompt "<what to analyze>" \
  [--persist-to "<path>.md"]
```

`--target-dir` must be an absolute path to an existing directory. The first time a directory is used, the wrapper auto-adds it to `~/.gemini/trustedFolders.json` (a one-time setup; surfaced as `auto_trusted` in `warnings[]`).

`--persist-to <path>.md` (optional): also write the response to a Markdown file under `$HOME` or `$CWD`. Useful for cross-session reuse — a later Claude session can read the file directly instead of re-running the query.

## Output

A single JSON envelope on stdout:

```json
{
  "ok": true,
  "mode": "analyze",
  "model_used": "gemini-3-pro-preview",
  "fallback_triggered": false,
  "attempts": [{"model": "...", "exit_code": 0, "duration_ms": 14200}],
  "response": "<Gemini's analysis verbatim>",
  "stats": {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "total_tokens": 0},
  "tool_calls": [{"name": "read_file", "..." : "..."}],
  "persisted_to": "<path or null>",
  "warnings": []
}
```

On failure, `ok: false` with `error.kind` in `{auth, bad_input, quota_exhausted, timeout, config, turn_limit, malformed_output, general}`. See [docs/usage.md](../../docs/usage.md) for the full envelope schema and error matrix.

## When NOT to use

- For real-time research with web grounding → use `gemini-bridge:research`
- For having Gemini blind-review a plan or PR → use `gemini-bridge:second-opinion`
- For analyzing images / PDFs / video frames → use `gemini-bridge:multimodal`
- When the user wants Claude to **edit** files — Gemini runs strictly read-only here
- When the codebase is small enough for Claude to read directly — saves a subprocess and Gemini quota

## Cost & quota

Each call burns Gemini quota proportional to `stats.total_tokens`. The wrapper falls back through `gemini-3-pro-preview` → `gemini-2.5-pro` → `gemini-2.5-flash` only on `quota_exhausted` / `timeout` — never on auth, bad input, or config errors. Surface `stats.total_tokens` to the user if a single call is unexpectedly large.
