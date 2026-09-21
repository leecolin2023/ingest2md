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
from ingest2md.media.audio import probe_media_info
from ingest2md.model import Document
from ingest2md.transcription.service import transcribe_audio
from ingest2md.transcription.writers import render_markdown

logger = logging.getLogger(__name__)


class DouyinExtractor:
    name = "抖音视频"
    description = "抖音单视频 / 分享短链 → 浏览器详情响应或 DOM 媒体地址 → ASR → Markdown"
    acquisition_plan = (
        "用现有 Playwright 打开抖音分享短链或单视频页面",
        "优先读取浏览器已经签名的详情响应，回退到 DOM 暴露的 http(s) 媒体地址",
        "逐个下载并验证音轨/时长后进入配置的 ASR backend（默认 SenseVoice 本地）",
        "如果页面只暴露 blob/登录墙则明确提示 Cookie 或本地文件 fallback",
    )

    def __init__(self, settings: Settings | None = None, runtime=None):
        self.settings = settings
        self.runtime = runtime

    def match(self, url: str) -> bool:
        return source.is_douyin_url(url)

    async def extract(self, url: str, output_dir: Path) -> Document:
        settings = self.settings or load_settings()
        cookie_file = settings.douyin_cookies_file or settings.cookies_file

        logger.info("抖音：使用浏览器页面解析公开媒体地址")
        meta = (
            await source.resolve_video_page(
                url, cookie_file, browser_runtime=self.runtime.browser,
            )
            if self.runtime is not None
            else await source.resolve_video_page(url, cookie_file)
        )

        with tempfile.TemporaryDirectory(prefix="ingest2md-douyin-") as temp:
            work = Path(temp)
            headers = {"Referer": meta["canonical_url"]}
            if meta.get("cookie_header"):
                headers["Cookie"] = meta["cookie_header"]

            media_path = None
            media_info = None
            candidate_errors = []
            candidates = meta.get("media_candidates") or [meta["media_url"]]
            try:
                expected_duration = float(meta.get("duration") or 0)
            except (TypeError, ValueError):
                expected_duration = 0.0

            for index, candidate in enumerate(candidates):
                downloaded = None
                try:
                    downloaded = await asyncio.to_thread(
                        download_url,
                        candidate,
                        work / f"media_{index:02d}.bin",
                        headers=headers,
                    )
                    candidate_info = await asyncio.to_thread(probe_media_info, str(downloaded))
                    actual_duration = float(candidate_info.get("duration") or 0)
                    if not candidate_info["has_audio"]:
                        candidate_errors.append(f"候选 {index + 1} 无音轨")
                        logger.warning("抖音：跳过无音轨媒体候选 %s", index + 1)
                        downloaded.unlink(missing_ok=True)
                        continue
                    if actual_duration <= 0.5:
                        candidate_errors.append(f"候选 {index + 1} 时长异常")
                        logger.warning("抖音：跳过时长异常媒体候选 %s", index + 1)
                        downloaded.unlink(missing_ok=True)
                        continue
                    if expected_duration >= 3 and actual_duration < expected_duration * 0.5:
                        candidate_errors.append(
                            f"候选 {index + 1} 时长过短 "
                            f"({actual_duration:.1f}s / 预期约 {expected_duration:.1f}s)"
                        )
                        logger.warning(
                            "抖音：跳过明显过短媒体候选 %s (%.1fs / 预期约 %.1fs)",
                            index + 1, actual_duration, expected_duration,
                        )
                        downloaded.unlink(missing_ok=True)
                        continue
                    media_path = downloaded
                    media_info = candidate_info
                    break
                except Exception as exc:
                    if downloaded is not None:
                        downloaded.unlink(missing_ok=True)
                    candidate_errors.append(f"候选 {index + 1}: {exc}")
                    logger.warning("抖音：媒体候选 %s 不可用: %s", index + 1, exc)
            if media_path is None:
                blob_hint = "；页面同时存在 blob 播放器" if meta.get("saw_blob") else ""
                detail = "；".join(candidate_errors[-3:])
                raise RuntimeError(
                    f"抖音媒体候选均不可用于转写{blob_hint}。{detail}。"
                    "请更新 Cookie，或下载视频后走本地媒体通道。"
                )
            if self.runtime is not None:
                transcript = await asyncio.to_thread(
                    transcribe_audio,
                    str(media_path),
                    work,
                    settings,
                    self.runtime.asr_backend,
                )
            else:
                transcript = await asyncio.to_thread(
                    transcribe_audio,
                    str(media_path),
                    work,
                    settings,
                )

            metadata = [
                ("来源", "抖音"),
                ("内容获取", meta.get("acquisition") or "Playwright DOM 媒体地址"),
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
            body_parts.append("## 转写正文\n\n" + render_markdown(transcript, window_seconds=settings.transcript_window_seconds))

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
                str(media_path),
                work,
                output_dir,
                settings,
                retained_filename="source_media.bin",
            )
            return doc