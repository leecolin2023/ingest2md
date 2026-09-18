"""Small HTML -> Markdown helpers shared by web-like extractors."""
from __future__ import annotations

import re
from bs4 import BeautifulSoup
from markdownify import markdownify as _markdownify

_DROP_TAGS = {"script", "style", "noscript", "svg", "form", "button", "iframe"}


def clean_fragment(html: str) -> str:
    """Convert an HTML fragment to readable Markdown without site chrome."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = _markdownify(str(soup), heading_style="ATX", bullets="-")
    text = re.sub(r"\n[ \t]+\n", "\n\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def text_of_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return " ".join(soup.stripped_strings)
