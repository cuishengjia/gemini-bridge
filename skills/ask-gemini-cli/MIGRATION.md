# Migration: project-local → user-global

Until v1 stabilizes, this skill lives at:

    <repo>/skills/ask-gemini-cli/

After stabilization, migrate to user-global:

    ~/.claude/skills/ask-gemini-cli/

## Checklist

1. Verify Phase 10 path audit passes (no hardcoded absolute repo paths).
2. `cp -R <repo>/skills/ask-gemini-cli ~/.claude/skills/`
3. Verify `~/.claude/skills/ask-gemini-cli/bin/ask-gemini` is executable.
4. Restart Claude Code; confirm `/ask-gemini-cli` is discoverable.
5. Run live smoke test (see `docs/test-report.md`).
6. Remove the project-local copy once global install is confirmed working.

## Non-portable bits to audit before migration

- `GEMINI_BIN` default: `/opt/homebrew/bin/gemini` (macOS Apple Silicon Homebrew). On Linux this is usually `/usr/local/bin/gemini` or `~/.local/bin/gemini`. Wrapper must honor `GEMINI_BIN` env override.
- Log directory: `~/.cache/ask-gemini-cli/` — POSIX-only; Windows users must set `ASK_GEMINI_CACHE_DIR`.
- All paths inside the skill are derived via `Path(__file__).resolve().parent` — never hardcoded.
