"""Extractor contract — the extension point for new channels.

To add a channel:

1. Create ``ingest2md/extractors/<name>.py`` implementing :class:`Extractor`.
2. Register it in ``ingest2md/extractors/__init__.py`` before Generic Web.

Nothing else in the extraction/output pipeline needs to change.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ingest2md.model import Document


class SourceUnavailableError(RuntimeError):
    """A source was recognized, but this version intentionally cannot fetch it."""

    def __init__(self, source_name: str, suggestion: str):
        self.source_name = source_name
        self.suggestion = suggestion
        super().__init__(
            f"已识别来源：{source_name}\n"
            "当前版本暂未接入稳定的媒体获取方式。\n"
            "建议下载视频后执行：\n"
            f'ingest2md "{suggestion}"'
        )


@runtime_checkable
class Extractor(Protocol):
    """One extraction channel for a class of URLs or content references."""

    name: str
    description: str

    def match(self, reference: str) -> bool:
        """Return True if this channel can extract ``reference``."""
        ...

    async def extract(self, reference: str, output_dir) -> Document:
        """Fetch/read ``reference`` and return a :class:`Document`."""
        ...
