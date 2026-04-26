"""Unit tests for lib.citations — Gemini grounding-redirect URL resolution."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from lib import citations  # noqa: E402


# ----------------------------------------------------------------------
# GROUNDING_PATTERN — what counts as a grounding redirect URL
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc123",
        "http://vertexaisearch.cloud.google.com/grounding-api-redirect/x_y-z.qq",
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AQXblrTokenABC%3D",
    ],
)
def test_pattern_matches_known_grounding_redirect_shapes(url: str) -> None:
    assert citations.GROUNDING_PATTERN.fullmatch(url) is not None


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/foo",
        "https://google.com/search?q=a",
        "https://vertexaisearch.cloud.google.com/other-endpoint/x",  # different path
        "ftp://vertexaisearch.cloud.google.com/grounding-api-redirect/x",  # not http(s)
    ],
)
def test_pattern_rejects_unrelated_urls(url: str) -> None:
    assert citations.GROUNDING_PATTERN.fullmatch(url) is None


def test_pattern_does_not_consume_trailing_punctuation() -> None:
    """URLs in prose like 'see (https://...).' shouldn't grab the closing paren."""
    text = "(https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc)."
    matches = citations.GROUNDING_PATTERN.findall(text)
    assert len(matches) == 1
    assert matches[0].endswith("abc")
    assert ")" not in matches[0]


# ----------------------------------------------------------------------
# resolve_grounding_urls — happy path / opt-out / no-op
# ----------------------------------------------------------------------

def test_resolve_returns_unchanged_when_no_grounding_urls() -> None:
    text = "Some response with https://example.com/article and no redirect."
    result, count = citations.resolve_grounding_urls(text)
    assert result == text
    assert count == 0


def test_resolve_opt_out_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """ASK_GEMINI_NO_RESOLVE_CITATIONS=1 short-circuits, no network calls."""
    monkeypatch.setenv("ASK_GEMINI_NO_RESOLVE_CITATIONS", "1")
    text = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
    with mock.patch.object(citations, "_resolve_one") as resolver:
        result, count = citations.resolve_grounding_urls(text)
    assert result == text
    assert count == 0
    resolver.assert_not_called()


def test_resolve_empty_string_is_safe() -> None:
    result, count = citations.resolve_grounding_urls("")
    assert result == ""
    assert count == 0


def test_resolve_replaces_single_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASK_GEMINI_NO_RESOLVE_CITATIONS", raising=False)
    text = "Source: https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
    fake = lambda u: (u, "https://www.bloomberg.com/news/articles/xyz")  # noqa: E731
    monkeypatch.setattr(citations, "_resolve_one", fake)
    result, count = citations.resolve_grounding_urls(text)
    assert "bloomberg.com" in result
    assert "vertexaisearch.cloud.google.com" not in result
    assert count == 1


def test_resolve_replaces_multiple_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASK_GEMINI_NO_RESOLVE_CITATIONS", raising=False)
    text = (
        "Source A: https://vertexaisearch.cloud.google.com/grounding-api-redirect/a "
        "Source B: https://vertexaisearch.cloud.google.com/grounding-api-redirect/b"
    )
    mapping = {
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a": "https://reuters.com/x",
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/b": "https://ft.com/y",
    }
    monkeypatch.setattr(citations, "_resolve_one", lambda u: (u, mapping[u]))
    result, count = citations.resolve_grounding_urls(text)
    assert "reuters.com/x" in result
    assert "ft.com/y" in result
    assert count == 2


def test_resolve_preserves_url_when_resolver_returns_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If resolver returns (url, url), no replacement should happen."""
    monkeypatch.delenv("ASK_GEMINI_NO_RESOLVE_CITATIONS", raising=False)
    text = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
    monkeypatch.setattr(citations, "_resolve_one", lambda u: (u, u))
    result, count = citations.resolve_grounding_urls(text)
    assert result == text
    assert count == 0


def test_resolve_idempotent_on_already_resolved_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running resolve twice on the result is a no-op."""
    monkeypatch.delenv("ASK_GEMINI_NO_RESOLVE_CITATIONS", raising=False)
    text = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a"
    monkeypatch.setattr(citations, "_resolve_one", lambda u: (u, "https://reuters.com/x"))
    once, _ = citations.resolve_grounding_urls(text)

    # Second call: with no grounding URLs left, resolver should NOT be called
    monkeypatch.setattr(
        citations, "_resolve_one", lambda u: (_ for _ in ()).throw(AssertionError("must not run"))
    )
    twice, count = citations.resolve_grounding_urls(once)
    assert twice == once
    assert count == 0


# ----------------------------------------------------------------------
# _resolve_one — network behavior under mocked urllib
# ----------------------------------------------------------------------

def _http_error_with_location(code: int, location: str | None) -> "urllib.error.HTTPError":  # noqa: F821
    """Build an HTTPError with a Location header (or none)."""
    import email.message
    import urllib.error

    headers = email.message.Message()
    if location is not None:
        headers["Location"] = location
    return urllib.error.HTTPError(
        url="http://x", code=code, msg="Found", hdrs=headers, fp=None
    )


def test_resolve_one_follows_302_to_location() -> None:
    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a"
    target = "https://www.bloomberg.com/article"

    def fake_open(self, req, timeout):  # noqa: ARG001
        raise _http_error_with_location(302, target)

    with mock.patch("urllib.request.OpenerDirector.open", fake_open):
        original, resolved = citations._resolve_one(url)
    assert original == url
    assert resolved == target


def test_resolve_one_returns_original_on_non_redirect_status() -> None:
    """A non-redirect HTTPError (e.g., 404) leaves the URL alone."""
    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a"

    def fake_open(self, req, timeout):  # noqa: ARG001
        raise _http_error_with_location(404, None)

    with mock.patch("urllib.request.OpenerDirector.open", fake_open):
        original, resolved = citations._resolve_one(url)
    assert resolved == url


def test_resolve_one_returns_original_on_url_error() -> None:
    """Network failure (URLError) leaves the URL alone — graceful degradation."""
    import urllib.error

    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a"

    def fake_open(self, req, timeout):  # noqa: ARG001
        raise urllib.error.URLError("DNS resolution failed")

    with mock.patch("urllib.request.OpenerDirector.open", fake_open):
        original, resolved = citations._resolve_one(url)
    assert resolved == url


def test_resolve_one_returns_original_on_timeout() -> None:
    """Slow networks leave the URL alone."""
    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a"

    def fake_open(self, req, timeout):  # noqa: ARG001
        raise TimeoutError("read timed out")

    with mock.patch("urllib.request.OpenerDirector.open", fake_open):
        original, resolved = citations._resolve_one(url)
    assert resolved == url


def test_resolve_one_handles_redirect_with_no_location_header() -> None:
    """Some buggy servers send a 302 without Location — fail gracefully."""
    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a"

    def fake_open(self, req, timeout):  # noqa: ARG001
        raise _http_error_with_location(302, None)

    with mock.patch("urllib.request.OpenerDirector.open", fake_open):
        original, resolved = citations._resolve_one(url)
    assert resolved == url


def test_resolve_one_returns_original_on_200_ok() -> None:
    """200 OK (no redirect) means the URL doesn't redirect — keep original."""
    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a"

    class _FakeResp:
        pass

    def fake_open(self, req, timeout):  # noqa: ARG001
        return _FakeResp()

    with mock.patch("urllib.request.OpenerDirector.open", fake_open):
        original, resolved = citations._resolve_one(url)
    assert resolved == url
