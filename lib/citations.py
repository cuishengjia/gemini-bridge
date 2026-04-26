"""Resolve Gemini grounding redirect URLs to their final destination URLs.

Gemini's `google_web_search` tool returns citations as
`vertexaisearch.cloud.google.com/grounding-api-redirect/<token>` URLs that
HTTP-redirect (302) to the actual sources (news outlets, blogs, papers,
etc.). Google requires the redirect for attribution tracking, but the raw
redirect URLs are opaque — users can't tell if a citation is from Bloomberg,
Reuters, a random blog, or a known-low-quality source.

This module scans the response text for these redirect URLs and follows
each one to its final destination, replacing the URL in-place. Network-
bound; uses parallel HEAD requests with a tight timeout. Failures
(timeout, non-redirect, network error) leave the original URL intact —
graceful degradation so a flaky network never blocks the success path.

Set `ASK_GEMINI_NO_RESOLVE_CITATIONS=1` to skip resolution entirely
(useful in offline / air-gapped environments).
"""

from __future__ import annotations

import concurrent.futures
import os
import re
import urllib.error
import urllib.request

# Match grounding redirect URLs. Stops at common non-URL characters so
# Markdown link syntax `[text](url)` and plain prose don't grab adjacent
# punctuation into the URL.
GROUNDING_PATTERN = re.compile(
    r"https?://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/"
    r"[A-Za-z0-9_\-./%~:?&=+]+"
)

# Per-URL timeout. Keep tight: a slow network shouldn't compound across
# 7+ citations. Total wall-clock = max(per-URL) thanks to parallel
# resolution below, not sum.
RESOLVE_TIMEOUT = 5.0
MAX_PARALLEL = 8

# Browser-ish UA. The redirect endpoint serves 302s to anything but some
# CDN edges block obvious bot UAs without one.
_USER_AGENT = "ask-gemini-cli/1 (+https://github.com/cuishengjia/gemini-bridge)"


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Block urllib's default follow-redirects so we can capture Location."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def _resolve_one(url: str) -> tuple[str, str]:
    """Resolve a single redirect URL.

    Returns (original_url, resolved_or_original). If resolution fails for
    any reason, returns the input verbatim — the caller can detect "no
    change" by checking equality.
    """
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _USER_AGENT})
        opener = urllib.request.build_opener(_NoRedirectHandler())
        opener.open(req, timeout=RESOLVE_TIMEOUT)
        # 200 OK with no redirect — return original.
        return (url, url)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            location = e.headers.get("Location") if e.headers else None
            if location:
                return (url, location)
        return (url, url)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return (url, url)


def resolve_grounding_urls(text: str) -> tuple[str, int]:
    """Replace Gemini grounding redirect URLs with their final destinations.

    Returns (modified_text, num_resolved). When
    `ASK_GEMINI_NO_RESOLVE_CITATIONS=1` is set, returns (text, 0) without
    any network calls.

    Idempotent: a second call on the resolved text is a no-op (no redirect
    URLs left to resolve).
    """
    if os.environ.get("ASK_GEMINI_NO_RESOLVE_CITATIONS") == "1":
        return (text, 0)
    if not text:
        return (text, 0)

    urls = list(set(GROUNDING_PATTERN.findall(text)))
    if not urls:
        return (text, 0)

    resolved_count = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            results = list(pool.map(_resolve_one, urls))
    except (RuntimeError, OSError):
        # Thread-pool spawn failed (rare; e.g., resource limits). Skip
        # resolution rather than failing the whole call.
        return (text, 0)

    for original, resolved in results:
        if original != resolved:
            text = text.replace(original, resolved)
            resolved_count += 1

    return (text, resolved_count)
