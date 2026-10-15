"""Recognize intentionally deferred media platforms before Generic Web."""
from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import urlparse

from ingest2md.extractors.base import SourceUnavailableError
from ingest2md.urlutils import host_of

_WEIXIN_CHANNEL_HOSTS = {"channels.weixin.qq.com"}


class DeferredMediaExtractor:
    name = "暂未接入的媒体平台"
    description = "微信视频号：识别来源并提示下载后走本地媒体通道"

    def match(self, url: str) -> bool:
        host = host_of(url)
        if host in _WEIXIN_CHANNEL_HOSTS:
            return True
        if host in {"weixin.qq.com", "www.weixin.qq.com", "mp.weixin.qq.com"}:
            path = PurePosixPath(urlparse(url).path).as_posix().lower()
            return path == "/sph" or path.startswith("/sph/")
        return False

    async def extract(self, url: str, output_dir):
        raise SourceUnavailableError("微信视频号", "/path/to/video.mp4")
