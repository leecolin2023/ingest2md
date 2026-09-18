"""Built-in channel registry. More specific sources must come before Generic Web."""
from __future__ import annotations

from ingest2md.extractors.base import Extractor
from ingest2md.extractors.deferred_media import DeferredMediaExtractor
from ingest2md.extractors.local_media import LocalMediaExtractor
from ingest2md.extractors.document import DocumentExtractor
from ingest2md.extractors.bilibili import BilibiliExtractor
from ingest2md.extractors.wechat import WeChatExtractor
from ingest2md.extractors.xiaoyuzhou import XiaoyuzhouExtractor
from ingest2md.extractors.youtube import YouTubeExtractor
from ingest2md.extractors.zhihu import ZhihuExtractor
from ingest2md.extractors.xiaohongshu import XiaohongshuExtractor
from ingest2md.extractors.web import GenericWebExtractor

_EXTRACTORS: list[Extractor] = [
    DeferredMediaExtractor(),
    LocalMediaExtractor(),
    DocumentExtractor(),
    WeChatExtractor(),
    BilibiliExtractor(),
    YouTubeExtractor(),
    XiaoyuzhouExtractor(),
    ZhihuExtractor(),
    XiaohongshuExtractor(),
    GenericWebExtractor(),
]


def get_extractors() -> list[Extractor]:
    return list(_EXTRACTORS)


def register(extractor: Extractor) -> None:
    # Third-party registrations are appended for backwards compatibility.
    # Callers that need to outrank Generic Web should own a custom registry.
    _EXTRACTORS.append(extractor)
