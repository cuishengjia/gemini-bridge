"""Unit tests for lib.persist.persist_response."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from lib import persist  # noqa: E402


@pytest.fixture(autouse=True)
def _home_to_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """H3 validation requires persist targets under $HOME or $CWD.

    Pytest's `tmp_path` on macOS lives under `/private/var/folders/...`, which
    is not under the real $HOME. Repoint $HOME at tmp_path so the existing
    tests (which write into tmp_path) stay valid, while still exercising the
    resolve()-based containment check.
    """
    monkeypatch.setenv("HOME", str(tmp_path))


def test_persist_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "a" / "b" / "out.md"
    result = persist.persist_response(
        target=target, mode="analyze", prompt="hi", response="hello",
        model_used="gemini-3-pro-preview",
    )
    assert Path(result).exists()
    assert Path(result) == target.resolve()


def test_persist_overwrites_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    target.write_text("OLD", encoding="utf-8")
    persist.persist_response(
        target=target, mode="analyze", prompt="p", response="NEW-BODY",
        model_used="m",
    )
    text = target.read_text(encoding="utf-8")
    assert "OLD" not in text
    assert "NEW-BODY" in text


def test_persist_writes_markdown_header_and_sections(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    persist.persist_response(
        target=target, mode="research", prompt="what time", response="resp-body",
        model_used="gemini-2.5-pro",
        stats={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# ask-gemini-cli output")
    assert "- mode: research" in text
    assert "- model: gemini-2.5-pro" in text
    assert "## Prompt" in text
    assert "## Response" in text
    assert "input=10 output=5 total=15" in text
    assert "resp-body" in text


def test_persist_stats_absent_writes_zeros(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    persist.persist_response(
        target=target, mode="analyze", prompt="p", response="r",
        model_used="m", stats=None,
    )
    text = target.read_text(encoding="utf-8")
    assert "input=0 output=0 total=0" in text


def test_persist_handles_non_ascii_response(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    persist.persist_response(
        target=target, mode="research",
        prompt="中文提示", response="答复: 你好，世界 🌏",
        model_used="gemini-3-pro-preview",
    )
    text = target.read_text(encoding="utf-8")
    assert "答复: 你好，世界 🌏" in text
    assert "中文提示" in text


def test_persist_returns_absolute_path_string(tmp_path: Path) -> None:
    target = tmp_path / "rel.md"
    result = persist.persist_response(
        target=target, mode="analyze", prompt="p", response="r",
        model_used="m",
    )
    assert isinstance(result, str)
    assert Path(result).is_absolute()


# --------------------------------------------------------------------------- #
# _format_stats_line edge cases
# --------------------------------------------------------------------------- #

def test_format_stats_line_non_dict() -> None:
    assert persist._format_stats_line("not a dict") == "input=0 output=0 total=0"
    assert persist._format_stats_line(None) == "input=0 output=0 total=0"
    assert persist._format_stats_line(42) == "input=0 output=0 total=0"


def test_format_stats_line_bad_input_tokens() -> None:
    line = persist._format_stats_line({"input_tokens": "oops"})
    assert "input=0" in line


def test_format_stats_line_bad_output_tokens() -> None:
    line = persist._format_stats_line(
        {"input_tokens": 5, "output_tokens": "bad", "total_tokens": 10}
    )
    assert "input=5" in line
    assert "output=0" in line
    assert "total=10" in line


def test_format_stats_line_bad_total_tokens() -> None:
    line = persist._format_stats_line(
        {"input_tokens": 5, "output_tokens": 3, "total_tokens": "x"}
    )
    assert "total=0" in line


def test_format_stats_line_none_values() -> None:
    line = persist._format_stats_line(
        {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    )
    assert line == "input=0 output=0 total=0"


# --------------------------------------------------------------------------- #
# H3: --persist-to target validation
# --------------------------------------------------------------------------- #

def test_validate_rejects_non_md_suffix(tmp_path: Path) -> None:
    """Non-.md suffixes must be rejected to avoid accidental overwrites of source
    files, configs, or arbitrary binaries. The wrapper is a Markdown writer."""
    with pytest.raises(ValueError, match=r"\.md"):
        persist._validate_persist_target(tmp_path / "out.txt")


def test_validate_rejects_missing_suffix(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\.md"):
        persist._validate_persist_target(tmp_path / "out")


def test_validate_accepts_md_uppercase_suffix(tmp_path: Path) -> None:
    """Suffix check is case-insensitive: out.MD is still Markdown."""
    # Must not raise.
    persist._validate_persist_target(tmp_path / "out.MD")


def test_validate_rejects_parent_outside_home_and_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Targets whose resolved parent is outside $HOME and CWD must be refused."""
    forbidden_home = tmp_path / "fake-home"
    forbidden_home.mkdir()
    outside = tmp_path / "somewhere-else"
    outside.mkdir()

    monkeypatch.setenv("HOME", str(forbidden_home))
    monkeypatch.chdir(forbidden_home)

    with pytest.raises(ValueError, match="outside allowed roots"):
        persist._validate_persist_target(outside / "out.md")


def test_validate_accepts_under_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # Must not raise.
    persist._validate_persist_target(home / "sub" / "out.md")


def test_validate_accepts_under_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    elsewhere = tmp_path / "home"
    elsewhere.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("HOME", str(elsewhere))
    monkeypatch.chdir(work)
    # Target under CWD but not under HOME — must still be accepted.
    persist._validate_persist_target(work / "out.md")


def test_persist_response_rejects_unsafe_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """persist_response must refuse before writing when the target is unsafe."""
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(home)

    with pytest.raises(ValueError):
        persist.persist_response(
            target=outside / "out.md", mode="analyze",
            prompt="p", response="r", model_used="m",
        )
    # Nothing should have been written.
    assert not (outside / "out.md").exists()
