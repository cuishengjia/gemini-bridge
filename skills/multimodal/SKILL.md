---
name: multimodal
description: Delegate analysis of non-text inputs — images, PDFs, video frames — to Google's Gemini CLI when Claude needs visual or document understanding. Pass an image or PDF path plus a prompt describing what to analyze. The wrapper handles Gemini's @file-reference syntax and policy access. Returns a single JSON envelope with the visual analysis. Invoke when the user provides a screenshot, UI mockup, diagram, scanned document, or video frame and asks for analysis, OCR, layout description, or visual comparison. Do NOT invoke for plain-text files (use analyze instead), or when Claude already has multimodal access to the same content.
---

# gemini-bridge:multimodal

Image / PDF / video frame analysis via Gemini CLI's multimodal capabilities.

## When to use

- User attaches or references a **screenshot, UI mockup, diagram, photo, or video frame** and asks for analysis
- User has a **PDF** (scanned document, paper, form) that needs OCR or content extraction
- User wants visual comparison ("is screenshot A similar to mockup B?")
- User asks "what's in this image / what does this UI do / extract text from this PDF"

## Invocation

The wrapper is `bin/ask-gemini` inside the installed plugin directory.
Claude Code lays the plugin out at one of:
`~/.claude/plugins/marketplaces/gemini-bridge/bin/ask-gemini` (when the
plugin was installed from a git source whose URL matches the marketplace),
or `~/.claude/plugins/cache/gemini-bridge/<version>/bin/ask-gemini` (when
installed as a separate clone). Use this single-shot `find` to resolve
the binary regardless of layout, so the first call always succeeds without
needing a `$CLAUDE_PLUGIN_ROOT` retry:

```bash
# Image (PNG, JPEG, WebP, etc.)
"$(find ~/.claude/plugins -path '*gemini-bridge*/bin/ask-gemini' -type f -executable 2>/dev/null | head -1)" \
  --mode multimodal \
  --image "<absolute path to image>" \
  --prompt "<what to analyze>" \
  [--persist-to "<path>.md"]

# PDF
"$(find ~/.claude/plugins -path '*gemini-bridge*/bin/ask-gemini' -type f -executable 2>/dev/null | head -1)" \
  --mode multimodal \
  --pdf "<absolute path to PDF>" \
  --prompt "<what to analyze>" \
  [--persist-to "<path>.md"]
```

Pass exactly **one** of `--image` or `--pdf` (not both). The wrapper:
1. Embeds the file via Gemini's `@<absolute_path>` reference syntax inside the prompt
2. Injects the file's parent directory as `--include-directories` so the read-only policy can reach the file
3. Enforces the same allow/deny policy as other modes — Gemini still cannot write or run shell

## Output

A single JSON envelope on stdout. The `response` field contains Gemini's visual / document analysis.

```json
{
  "ok": true,
  "mode": "multimodal",
  "model_used": "gemini-3-pro-preview",
  "response": "<analysis>",
  "stats": {"...": "..."},
  "tool_calls": [],
  "...": "..."
}
```

`tool_calls` is usually empty for multimodal — Gemini reads the embedded file directly without invoking `read_file`.

On failure, `ok: false` with `error.kind` from the standard set. Common failures:
- `bad_input` — file not found, or both `--image` and `--pdf` passed
- `quota_exhausted` — visual models burn more quota than text; large images can exhaust faster
- `malformed_output` — rare, indicates Gemini CLI version drift

## When NOT to use

- For plain-text files → use `gemini-bridge:analyze` instead (cheaper, more flexible)
- For research questions about an image's subject → first analyze with this skill, then research with `gemini-bridge:research` using the extracted text
- For animations / videos longer than a few seconds — Gemini CLI's video support is frame-based; long videos exhaust quota fast

## Supported file types

- Images: PNG, JPEG, JPG, WebP, GIF (single frame)
- PDFs: any text or scanned PDF
- Video: extract a frame first (e.g., with `ffmpeg`) and pass as `--image`

The wrapper does not validate file format — Gemini will reject unsupported types with `bad_input`.
