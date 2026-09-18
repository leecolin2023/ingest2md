"""Content-reference routing: normalize then dispatch to the first matching channel."""
from __future__ import annotations

from ingest2md.extractors import get_extractors
from ingest2md.extractors.base import Extractor
from ingest2md.urlutils import host_of, normalize_reference, normalize_url

__all__ = [
    "UnsupportedURLError", "find_extractor", "host_of", "normalize_reference", "normalize_url"
]


class UnsupportedURLError(Exception):
    def __init__(self, reference: str, supported: list[Extractor]):
        lines = [f"暂不支持该输入类型: {reference}", "", "当前支持的通道:"]
        lines.extend(f"  - {e.name}: {e.description}" for e in supported)
        super().__init__("\n".join(lines))
        self.reference = reference
        self.supported = supported


def find_extractor(reference: str) -> Extractor:
    supported = get_extractors()
    for extractor in supported:
        if extractor.match(reference):
            return extractor
    raise UnsupportedURLError(reference, supported)
