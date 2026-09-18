"""Input cleaning helpers shared by the CLI, router and extractors."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

_HTTP_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")
_TRAILING_PUNCTUATION = ",.;:!?，。；：！？、）)]】》〉」』\"'"


def _strip_wrapping_quotes(raw: str) -> str:
    return raw.strip().strip("\"'").strip()


def extract_first_url(raw: str) -> str:
    """Extract the first http(s) URL from a URL or an App sharing paragraph.

    The returned URL only receives conservative trailing-punctuation cleanup;
    query strings are otherwise left untouched.
    """
    match = _HTTP_URL_RE.search(raw or "")
    if not match:
        return ""
    return match.group(0).rstrip(_TRAILING_PUNCTUATION)


def existing_local_path(raw: str) -> str:
    """Return an absolute path only when ``raw`` is an existing local file.

    This deliberately refuses to classify a merely path-looking string as a
    local file. It prevents typos such as ``missing.mp4`` from entering the
    media pipeline and keeps URL/domain input backwards compatible.
    """
    value = _strip_wrapping_quotes(raw)
    if not value or "\n" in value or "\r" in value:
        return ""
    try:
        path = Path(value).expanduser()
        if path.is_file():
            return str(path.resolve())
    except (OSError, ValueError):
        pass
    return ""


def normalize_url(raw: str) -> str:
    """Normalize a URL, BV id, or sharing paragraph containing a URL.

    Repairs common terminal paste artifacts while keeping the old v0.4 URL
    behavior. For local files use :func:`normalize_reference` instead.
    """
    value = _strip_wrapping_quotes(raw)
    if _BV_RE.fullmatch(value):
        return f"https://www.bilibili.com/video/{value}"

    shared_url = extract_first_url(value)
    url = shared_url or value
    # Windows terminals often paste `\&` / `\?` escaped query separators.
    url = url.replace("\\&", "&").replace("\\?", "?")
    # Only unescape &amp; — full unescaping would corrupt query params like
    # &timestamp (&times is a valid HTML entity for ×).
    url = url.replace("&amp;", "&")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


def normalize_reference(raw: str) -> str:
    """Normalize one *content reference*.

    A reference can be an existing local file, a URL, a sharing paragraph that
    contains a URL, or a Bilibili BV id. Local files are resolved first so
    filenames containing URL-like text are never rewritten unexpectedly.
    """
    local = existing_local_path(raw)
    if local:
        return local
    return normalize_url(raw)


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
