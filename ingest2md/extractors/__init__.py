"""Built-in channel registry. More specific sources must come before Generic Web."""
from __future__ import annotations

from ingest2md.extractors.base import Extractor
from ingest2md.extractors.deferred_media import DeferredMediaExtractor
from ingest2md.extractors.douyin import DouyinExtractor
from ingest2md.extractors.local_media import LocalMediaExtractor
from ingest2md.extractors.document import DocumentExtractor
from ingest2md.extractors.bilibili import BilibiliExtractor
from ingest2md.extractors.wechat import WeChatExtractor
from ingest2md.extractors.xiaoyuzhou import XiaoyuzhouExtractor
from ingest2md.extractors.youtube import YouTubeExtractor
from ingest2md.extractors.zhihu import ZhihuExtractor
from ingest2md.extractors.xiaohongshu import XiaohongshuExtractor
from ingest2md.extractors.web import GenericWebExtractor

# One registry owns both ordering and Settings injection.
_BUILTIN_EXTRACTORS = [
    (DeferredMediaExtractor, False),
    (DouyinExtractor, True),
    (LocalMediaExtractor, True),
    (DocumentExtractor, False),
    (WeChatExtractor, False),
    (BilibiliExtractor, True),
    (YouTubeExtractor, True),
    (XiaoyuzhouExtractor, True),
    (ZhihuExtractor, True),
    (XiaohongshuExtractor, True),
    (GenericWebExtractor, False),
]
_REGISTERED_EXTRACTORS: list[Extractor] = []


def get_extractors(settings=None) -> list[Extractor]:
    builtins = [
        extractor_type(settings) if accepts_settings else extractor_type()
        for extractor_type, accepts_settings in _BUILTIN_EXTRACTORS
    ]
    return builtins + list(_REGISTERED_EXTRACTORS)


def register(extractor: Extractor) -> None:
    # Third-party registrations are appended for backwards compatibility.
    # Callers that need to outrank Generic Web should own a custom registry.
    _REGISTERED_EXTRACTORS.append(extractor)
