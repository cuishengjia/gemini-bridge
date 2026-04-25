---
name: second-opinion
description: Get a blind, independent critique of a plan, design, code patch, or technical decision from Google's Gemini CLI — a different model lineage with no access to Claude's reasoning. Pass the artefact (plan/diff/design doc) plus a problem statement; Gemini returns its independent assessment in a JSON envelope. CRITICAL invariant — the task field must describe the problem being solved, NOT Claude's reasoning, conclusions, or recommended solution. Leaking Claude's reasoning chain defeats the entire purpose. Invoke when the user wants a sanity-check from an independent critic before committing to a non-trivial plan or patch. Do NOT invoke for trivial decisions, when the artefact is too sensitive to share with a different vendor, or when speed matters more than independence.
---

# gemini-bridge:second-opinion

Blind independent critique by a different model lineage (Gemini), no shared reasoning with Claude.

## When to use

- User asks "get a second opinion on this plan / design / PR / patch"
- User wants to validate a non-trivial technical decision
- The problem benefits from cross-model perspective (e.g., security review, architectural choices, edge-case enumeration)
- Pre-commit sanity check on a complex patch

## Invocation

```bash
"$CLAUDE_PLUGIN_ROOT/bin/ask-gemini" \
  --mode second-opinion \
  --task "<problem statement, NOT solution>" \
  --artefact-file "<path to plan/diff/doc>" \
  [--persist-to "<path>.md"]
```

The wrapper reads `--artefact-file` and embeds it in the prompt verbatim. The `--task` field is what tells Gemini what problem the artefact tries to solve.

## CRITICAL — Blind review invariant

**`--task` must describe the PROBLEM, not Claude's solution.** The whole value of this skill is independent assessment. If you leak Claude's reasoning chain or proposed answer into `--task`, Gemini will anchor on it and the second opinion is worthless.

| ✅ Good `--task` | ❌ Bad `--task` |
|---|---|
| "Users report pagination skipping items when the dataset shrinks between requests; we need to decide how to stabilize pagination." | "I concluded we should use cursor pagination with a snapshot; please agree." |
| "This patch tries to fix a race condition in the connection pool; assess correctness and performance." | "I think the patch correctly fixes the race; please confirm and add any concerns." |
| "Evaluate whether this JWT scheme handles refresh-token rotation correctly." | "My implementation rotates refresh tokens on every request; verify it's right." |

The wrapper has no automatic check for this — the discipline is on Claude / the caller.

## Output

A single JSON envelope on stdout:

- `response` — Gemini's critique, ideally structured (strengths / weaknesses / risks / recommendations)
- `attempts` — model fallback chain (usually just one entry)
- `warnings` — may include `model_emitted_thought_events` if Gemini streamed CoT (filtered by the wrapper, not in the response)

On failure, `ok: false` with `error.kind` from the standard set.

## When NOT to use

- For analyzing a codebase scope → use `gemini-bridge:analyze`
- For web-grounded research → use `gemini-bridge:research`
- For images / PDFs → use `gemini-bridge:multimodal`
- When the artefact contains secrets that shouldn't go to a different vendor
- For trivial decisions where independence isn't worth a quota burn

## Tip: structuring the artefact

The artefact file should be self-contained — Gemini sees only what's in the file plus the `--task` string. Include enough context (relevant code sections, prior discussion, constraints) so Gemini doesn't have to guess. But don't include Claude's analysis or recommended path.

For PR-style artefacts: a unified diff (`git diff`) plus a brief problem statement at the top works well.
