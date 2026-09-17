"""Built-in channel registry. More specific sources must come before Generic Web."""
from __future__ import annotations

from url2md.extractors.base import Extractor
from url2md.extractors.deferred_media import DeferredMediaExtractor
from url2md.extractors.local_media import LocalMediaExtractor
from url2md.extractors.bilibili import BilibiliExtractor
from url2md.extractors.wechat import WeChatExtractor
from url2md.extractors.xiaoyuzhou import XiaoyuzhouExtractor
from url2md.extractors.youtube import YouTubeExtractor
from url2md.extractors.zhihu import ZhihuExtractor
from url2md.extractors.xiaohongshu import XiaohongshuExtractor
from url2md.extractors.web import GenericWebExtractor

_EXTRACTORS: list[Extractor] = [
    DeferredMediaExtractor(),
    LocalMediaExtractor(),
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
