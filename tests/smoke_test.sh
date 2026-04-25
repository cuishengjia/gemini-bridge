#!/usr/bin/env bash
# Live smoke tests for ask-gemini-cli (gated on ASK_GEMINI_LIVE=1).
#
# Runs one invocation per mode (analyze / research / second-opinion / multimodal)
# against a throwaway target at /tmp/ask-gemini-smoke/, saves each envelope to
# examples/<mode>.json, verifies ok:true via jq, and reports per-mode wall time.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ASK_GEMINI="$SKILL_DIR/bin/ask-gemini"
EXAMPLES_DIR="$SKILL_DIR/examples"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"
SMOKE_DIR="/tmp/ask-gemini-smoke"

# ---- Gate -----------------------------------------------------------------

if [ "${ASK_GEMINI_LIVE:-0}" != "1" ]; then
  echo "[smoke] ASK_GEMINI_LIVE is not 1; skipping live smoke tests."
  echo "[smoke] Re-run with: ASK_GEMINI_LIVE=1 GEMINI_API_KEY=... tests/smoke_test.sh"
  exit 0
fi

if [ -z "${GEMINI_API_KEY:-}" ] && [ ! -f "$HOME/.gemini/oauth_creds.json" ]; then
  echo "[smoke] No auth: set GEMINI_API_KEY or run 'gemini auth login'."
  exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "[smoke] jq not installed; install via 'brew install jq' to run smoke tests."
  exit 1
fi

# ---- Setup target ---------------------------------------------------------

rm -rf "$SMOKE_DIR"
mkdir -p "$SMOKE_DIR"
mkdir -p "$EXAMPLES_DIR"
mkdir -p "$FIXTURES_DIR"

cat > "$SMOKE_DIR/hello.py" <<'PY'
def hello(name: str = "world") -> str:
    """Return a friendly greeting."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(hello())
PY

cat > "$SMOKE_DIR/util.py" <<'PY'
def double(x: int) -> int:
    return x * 2


def is_empty(items) -> bool:
    return len(items) == 0
PY

cat > "$SMOKE_DIR/README.md" <<'MD'
# smoke target
Tiny sample project used only by tests/smoke_test.sh.
MD

# ---- Optional: test image for multimodal ----------------------------------

TEST_IMAGE="$FIXTURES_DIR/test_image.png"
MM_STATUS="pending"
if [ ! -f "$TEST_IMAGE" ]; then
  if python3 -c "import PIL" 2>/dev/null; then
    python3 -c "from PIL import Image; Image.new('RGB',(100,100),'red').save('$TEST_IMAGE')"
  else
    MM_STATUS="skipped_no_image"
  fi
fi

# ---- Run helpers ----------------------------------------------------------

run_mode() {
  local name="$1"; shift
  local outfile="$EXAMPLES_DIR/$name.json"
  local t0 t1
  t0=$(python3 -c "import time; print(time.monotonic())")
  "$ASK_GEMINI" "$@" > "$outfile" 2> "$outfile.stderr"
  local rc=$?
  t1=$(python3 -c "import time; print(time.monotonic())")
  local elapsed
  elapsed=$(python3 -c "print(f'{($t1 - $t0) * 1000:.0f}')")

  if [ $rc -ne 0 ] && [ $rc -ne 2 ] && [ $rc -ne 3 ]; then
    echo "[smoke:$name] FAILED — exit=$rc, elapsed=${elapsed}ms"
    echo "[smoke:$name] stderr:"; cat "$outfile.stderr"
    return 1
  fi

  if ! jq -e '.ok == true' "$outfile" >/dev/null; then
    echo "[smoke:$name] FAILED — envelope ok is false or missing, elapsed=${elapsed}ms"
    jq '.' "$outfile" || cat "$outfile"
    return 1
  fi

  local model used fb tokens
  model=$(jq -r '.model_used' "$outfile")
  fb=$(jq -r '.fallback_triggered' "$outfile")
  tokens=$(jq -r '.stats.total_tokens' "$outfile")
  echo "[smoke:$name] PASS model=$model fallback=$fb tokens=$tokens elapsed=${elapsed}ms → $outfile"
  return 0
}

EXIT_CODE=0

# ---- analyze --------------------------------------------------------------

if ! run_mode "analyze-repo" \
  --mode analyze \
  --target-dir "$SMOKE_DIR" \
  --prompt "What does this code do? Summarize in 3 sentences."; then
  EXIT_CODE=1
fi

# ---- research -------------------------------------------------------------

if ! run_mode "research-query" \
  --mode research \
  --query "What is the current stable version of Python?"; then
  EXIT_CODE=1
fi

# ---- second-opinion -------------------------------------------------------

if ! run_mode "second-opinion" \
  --mode second-opinion \
  --task "Decide if this tiny helper needs error handling for empty input." \
  --artefact-file "$SMOKE_DIR/util.py"; then
  EXIT_CODE=1
fi

# ---- multimodal -----------------------------------------------------------

if [ "$MM_STATUS" = "skipped_no_image" ] || [ ! -f "$TEST_IMAGE" ]; then
  echo "[smoke:multimodal] SKIPPED — no test image at $TEST_IMAGE (install PIL or drop one in fixtures/)"
else
  if ! run_mode "multimodal-screenshot" \
    --mode multimodal \
    --prompt "Describe this image in one sentence." \
    --image "$TEST_IMAGE"; then
    EXIT_CODE=1
  fi
fi

echo ""
if [ $EXIT_CODE -eq 0 ]; then
  echo "[smoke] All live smoke tests PASSED."
else
  echo "[smoke] One or more live smoke tests FAILED."
fi
exit $EXIT_CODE
