"""Douyin single video -> browser-resolved media -> shared ASR -> Markdown."""
from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ingest2md.config import Settings, load_settings
from ingest2md.extractors.video import retain_media
from ingest2md.media import douyin as source
from ingest2md.media.download import download_url
from ingest2md.model import Document
from ingest2md.transcription.service import transcribe_audio
from ingest2md.transcription.writers import render_markdown

logger = logging.getLogger(__name__)


class DouyinExtractor:
    name = "抖音视频"
    description = "抖音单视频 / 分享短链 → 浏览器 DOM 媒体地址 → ASR → Markdown"
    acquisition_plan = (
        "用现有 Playwright 打开抖音分享短链或单视频页面",
        "只读取 DOM 已暴露的 http(s) 视频地址；不实现 a_bogus/X-Bogus",
        "下载视频并进入配置的 ASR backend（默认 SenseVoice 本地）",
        "如果页面只暴露 blob/登录墙则明确提示 Cookie 或本地文件 fallback",
    )

    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    def match(self, url: str) -> bool:
        return source.is_douyin_url(url)

    async def extract(self, url: str, output_dir: Path) -> Document:
        settings = self.settings or load_settings()
        cookie_file = settings.douyin_cookies_file or settings.cookies_file

        logger.info("抖音：使用浏览器页面解析公开媒体地址")
        meta = await source.resolve_video_page(url, cookie_file)

        with tempfile.TemporaryDirectory(prefix="ingest2md-douyin-") as temp:
            work = Path(temp)
            headers = {"Referer": meta["canonical_url"]}
            if meta.get("cookie_header"):
                headers["Cookie"] = meta["cookie_header"]

            try:
                video_path = await asyncio.to_thread(
                    download_url,
                    meta["media_url"],
                    work / "video.mp4",
                    headers=headers,
                )
            except Exception as exc:
                raise RuntimeError(
                    "已从抖音页面取得媒体地址，但视频下载失败；"
                    "可尝试更新登录 Cookie，或下载视频后走本地媒体通道。"
                ) from exc
            transcript = await asyncio.to_thread(
                transcribe_audio,
                str(video_path),
                work,
                settings,
            )

            metadata = [
                ("来源", "抖音"),
                ("内容获取", "Playwright DOM 媒体地址"),
                ("ASR 后端", settings.asr_backend),
                ("已处理（秒）", str(transcript.processed_seconds)),
                ("转写时间", datetime.now(timezone.utc).isoformat(timespec="seconds")),
                ("转写模型", ", ".join(transcript.models)),
                ("语言", transcript.language or "原语言"),
                ("时间戳精度", transcript.timestamp_precision),
            ]
            if meta["author"]:
                metadata.insert(1, ("作者", meta["author"]))

            body_parts = []
            if meta["description"]:
                body_parts.append("## 视频简介\n\n" + meta["description"])
            body_parts.append("## 转写正文\n\n" + render_markdown(transcript))

            doc = Document(
                title=meta["title"],
                source_url=meta["canonical_url"],
                source_id=meta["video_id"],
                source_type="douyin",
                metadata=metadata,
                body_md="\n\n".join(body_parts),
                transcript=transcript,
                original_description=meta["description"],
            )
            retain_media(
                doc,
                str(video_path),
                work,
                output_dir,
                settings,
                retained_filename="video.mp4",
            )
            return doc
