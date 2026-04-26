---
name: research
description: Delegate web-grounded research to Google's Gemini CLI when the question requires fresh, post-training-cutoff information with verifiable URL citations. Gemini uses google_web_search and web_fetch (allowed by a read-only policy) and returns a single JSON envelope whose response includes inline URL citations and whose tool_calls field shows what queries fired. Invoke when the user asks for "current X", "latest Y", "what's the state of Z right now", recent news, library changelog lookups, or any fact where freshness matters. Do NOT invoke when the answer is stable training-data knowledge, when the user explicitly wants Claude's synthesis without fresh search, or when offline.
---

# gemini-bridge:research

Read-only web research with Google Search grounding via Gemini CLI.

## When to use

- User asks "what's the latest / current / newest X"
- Question requires post-training-cutoff information (new releases, recent incidents, current versions)
- User asks a factual question that should have URL citations
- User explicitly says "上网查 / search for / look up / research"

## Invocation

The wrapper is at `bin/ask-gemini` inside this plugin's installed directory.
Claude Code typically exports `$CLAUDE_PLUGIN_ROOT`; if that variable is empty
in your shell (some Claude Code versions don't propagate it to Bash tool
calls), the binary lives at
`~/.claude/plugins/cache/gemini-bridge/<version>/bin/ask-gemini`.

```bash
"$CLAUDE_PLUGIN_ROOT/bin/ask-gemini" \
  --mode research \
  --query "<the user's research question>" \
  [--target-dir "<absolute path>"] \
  [--persist-to "<path>.md"]
```

If `$CLAUDE_PLUGIN_ROOT` is not set, locate the script by listing
`~/.claude/plugins/cache/gemini-bridge/` and use the absolute path directly.

`--query` is the only required argument. `--target-dir` is optional — pass it when the research question is grounded in a specific codebase (e.g., "what's the latest version of X that's compatible with this project?"). `--persist-to` (optional, must end in `.md`, must resolve under `$HOME` or `$CWD`) saves the response for later reuse.

## Output

A single JSON envelope on stdout. Key fields:

- `response` — Gemini's answer, with inline URL citations
- `tool_calls` — list of `{name: "google_web_search" | "web_fetch", query/url: "..."}` showing what was searched and fetched. Useful for the user to verify the research path.
- `warnings` may include `zero_url_response` if Gemini returned no URLs (treat the answer with reduced trust)

On failure, `ok: false` with `error.kind` in `{auth, bad_input, quota_exhausted, timeout, config, turn_limit, malformed_output, general}`.

## When NOT to use

- For analyzing a codebase → use `gemini-bridge:analyze`
- For blind cross-model review → use `gemini-bridge:second-opinion`
- For images / PDFs → use `gemini-bridge:multimodal`
- When the answer is stable training-data knowledge (e.g., "what's the time complexity of binary search") — Claude can answer directly, saves a network round-trip and Gemini quota
- When offline — Gemini CLI requires a working network connection

## Quality signals to watch

- **`zero_url_response` warning** — Gemini answered without citing URLs. Almost always means the citation contract was ignored. Treat with caution; consider re-running with a tighter `--query`.
- **`tool_calls` empty** — No search ran. The response is essentially Gemini's training-data knowledge, no fresher than what Claude could have produced.

## Cost & quota

Same fallback chain as other modes (`3-pro-preview` → `2.5-pro` → `2.5-flash`); only quota / timeout triggers fallback. Research mode typically uses fewer input tokens than `analyze` but still consumes quota — don't use for trivial questions Claude can answer directly.
