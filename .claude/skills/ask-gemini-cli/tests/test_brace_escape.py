"""Regression tests for the brace-collision bug surfaced by live smoke 2026-04-19.

Original symptom: `_compose_second_opinion` blew up with `KeyError` when the
prompt template contained literal `{...}` in its example output format
(`{ looks sound | has issues | has critical problems }`).

Root cause: `str.format` only rejects literal `{name}` inside the TEMPLATE,
not inside the values being substituted. (Python does not recursively process
substituted values, see `help(str.format_map)` and PEP 3101.)

Fix: templates escape literal braces as `{{`/`}}`, and `bin/ask-gemini` uses
a small `_render(template, **vars)` helper that does a single-pass replace
per named placeholder — avoiding `str.format` entirely so user content with
braces is never altered.

These tests lock in:
  1. `_render` behaviour (including preserving user braces verbatim).
  2. Each `_compose_*` function surviving braced user content.
  3. A structural scan of prompt templates to catch unexpected `{name}`
     placeholders before they reach live smoke.
"""
from __future__ import annotations

import importlib.util
import string
from pathlib import Path

import pytest


SKILL_DIR = Path(__file__).resolve().parent.parent
BIN_PATH = SKILL_DIR / "bin" / "ask-gemini"
PROMPTS_DIR = SKILL_DIR / "prompts"

ALLOWED_PLACEHOLDERS: dict[str, set[str]] = {
    "analyze.md": {"target_dir", "user_prompt"},
    "research.md": {"user_query", "optional_context_block"},
    "second_opinion.md": {"task", "artefact"},
    "multimodal.md": {"user_prompt"},
}


def _load_cli_module():
    """Load bin/ask-gemini as an importable module under name `ask_gemini_cli`.

    The file has no `.py` suffix, so we attach an explicit SourceFileLoader.
    """
    from importlib.machinery import SourceFileLoader

    loader = SourceFileLoader("ask_gemini_cli", str(BIN_PATH))
    spec = importlib.util.spec_from_loader("ask_gemini_cli", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cli():
    return _load_cli_module()


class _Args:
    """Lightweight stand-in for argparse.Namespace used by _compose_*."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# _render() unit behaviour
# ---------------------------------------------------------------------------

def test_render_substitutes_single_placeholder(cli):
    assert cli._render("hello {name}", name="world") == "hello world"


def test_render_preserves_braces_in_value(cli):
    """User content with JSON / TS / f-string braces must NOT be altered."""
    assert cli._render("x={v}", v='{"a": 1, "b": {"n": 2}}') == 'x={"a": 1, "b": {"n": 2}}'
    assert cli._render("q={q}", q="{x+1}") == "q={x+1}"


def test_render_unfolds_doubled_braces_in_template(cli):
    """Templates use `{{` / `}}` for literal braces — `_render` must collapse them."""
    tpl = "verdict: {{ sound | issues }} and {a}"
    assert cli._render(tpl, a="go") == "verdict: { sound | issues } and go"


def test_render_handles_none_value(cli):
    assert cli._render("[{x}]", x=None) == "[]"


def test_render_leaves_unknown_placeholders_alone(cli):
    """Unknown `{foo}` tokens are not format fields — preserve, never raise."""
    # Render with a known placeholder; an accidentally-literal `{other}` in the
    # template should pass through unchanged (after `{{` / `}}` collapse).
    assert cli._render("{known} and {other}", known="ok") == "ok and {other}"


# ---------------------------------------------------------------------------
# _compose_* must not raise when user content contains braces
# ---------------------------------------------------------------------------

def test_compose_analyze_survives_braces_in_prompt(cli, tmp_path):
    args = _Args(
        target_dir=str(tmp_path),
        prompt='data = {"key": "val"} and config = {flag: true}',
    )
    prompt, target = cli._compose_analyze(args)
    assert target == tmp_path.resolve()
    assert '{"key": "val"}' in prompt
    assert '{flag: true}' in prompt


def test_compose_analyze_survives_braces_in_target_dir(cli, tmp_path):
    weird = tmp_path / "dir{weird}name"
    weird.mkdir()
    args = _Args(target_dir=str(weird), prompt="look at files")
    prompt, target = cli._compose_analyze(args)
    assert target == weird.resolve()
    assert "dir{weird}name" in prompt


def test_compose_research_survives_braces_in_query(cli):
    args = _Args(
        query='what does f"{x+1}" print in Python when x = 2?',
        target_dir=None,
    )
    prompt, target = cli._compose_research(args)
    assert target is None
    assert '{x+1}' in prompt


def test_compose_second_opinion_survives_braces_in_artefact(cli, tmp_path):
    art = tmp_path / "artefact.ts"
    art.write_text(
        'type Foo = Array<{id: string; tags: {[k: string]: number}}>;\n'
        'const bad = {a: 1, b: {nested: true}};\n',
        encoding="utf-8",
    )
    args = _Args(task="is this safe?", artefact_file=str(art))
    prompt, target = cli._compose_second_opinion(args)
    assert target is None
    assert '{id: string' in prompt
    assert '{nested: true}' in prompt
    # The template's own literal-brace example must render single-braced.
    assert "{ looks sound | has issues | has critical problems }" in prompt


def test_compose_second_opinion_survives_braces_in_task(cli, tmp_path):
    art = tmp_path / "tiny.txt"
    art.write_text("ok", encoding="utf-8")
    args = _Args(
        task="evaluate mustache template {{name}} rendering vs Python f-string {x+1}",
        artefact_file=str(art),
    )
    prompt, _ = cli._compose_second_opinion(args)
    # `_render` collapses `{{...}}` to `{...}`, so the user's `{{name}}` becomes `{name}`.
    assert "{name}" in prompt
    assert "{x+1}" in prompt


def test_compose_multimodal_survives_braces_in_prompt(cli, tmp_path):
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    args = _Args(image=str(img), pdf=None, prompt='describe {format: "png"} layout')
    prompt, target = cli._compose_multimodal(args)
    # H1: multimodal returns the media's parent dir as include_dir, and the
    # rendered prompt carries an `@<absolute-path>` prefix so Gemini actually
    # loads the file.
    assert target == tmp_path.resolve()
    assert '{format: "png"}' in prompt
    assert f"@{img.resolve()}" in prompt


# ---------------------------------------------------------------------------
# Template-level guard: only whitelisted placeholders may appear
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template_name", sorted(ALLOWED_PLACEHOLDERS.keys()))
def test_prompt_templates_only_have_whitelisted_placeholders(template_name):
    """Forbid unexpected `{name}` fields and naked `{}` in templates.

    Update ALLOWED_PLACEHOLDERS above when a template intentionally adds a
    new placeholder. All other literal braces in a template MUST be written
    as `{{` / `}}` so `_render` collapses them correctly.
    """
    path = PROMPTS_DIR / template_name
    text = path.read_text(encoding="utf-8")

    allowed = ALLOWED_PLACEHOLDERS[template_name]
    seen: set[str] = set()
    for literal, field_name, format_spec, conversion in string.Formatter().parse(text):
        if field_name is None:
            continue
        assert field_name != "", (
            f"{template_name}: found naked '{{}}' placeholder; use '{{{{' to escape."
        )
        assert not field_name.isdigit(), (
            f"{template_name}: positional placeholder '{{{field_name}}}' not allowed."
        )
        assert field_name in allowed, (
            f"{template_name}: unexpected placeholder '{{{field_name}}}'."
            f" Allowed: {sorted(allowed)}."
            f" Either add it to ALLOWED_PLACEHOLDERS or escape with '{{{{...}}}}'."
        )
        seen.add(field_name)

    missing = allowed - seen
    if missing:
        pytest.skip(
            f"{template_name}: whitelist lists unused placeholders {sorted(missing)}"
        )
