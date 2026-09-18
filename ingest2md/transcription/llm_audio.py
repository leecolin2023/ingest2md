"""Generic multimodal LLM audio backend.

Opencode Go is the default example configuration, not a hard-coded product
dependency. Any compatible chat/responses endpoint that accepts input_audio can
be configured through Settings.
"""
from __future__ import annotations

import base64
import logging
import time
import uuid
from pathlib import Path

import requests

from ingest2md import __version__
from ingest2md.config import Settings
from ingest2md.media.audio import chunk_audio_mp3
from ingest2md.transcription.model import Segment, TranscriptResult

logger = logging.getLogger(__name__)

TRANSCRIBE_PROMPT = (
    "请自动识别这段音频中的语言，按说话者使用的原语言逐字转写全部语音内容。多语言混说也保留各自原语言。要求：\n"
    "1) 完整保留所有原话，不要遗漏、不要总结、不要翻译、不要改写；\n"
    "2) 保留口语化表达，只添加适当的标点符号；\n"
    "3) 除转写文本外不要输出任何解释、注释或无关文字；\n"
    "4) 如果音频中没有语音，只输出：[无语音]"
)


class LLMAudioBackend:
    name = "llm"

    def __init__(self):
        self.used_models: list[str] = []
        self.working: dict | None = None
        self.session_id = str(uuid.uuid4())

    @staticmethod
    def _extract_text(text) -> str:
        if isinstance(text, list):
            text = "".join(item.get("text", "") for item in text if isinstance(item, dict))
        return (text or "").strip()

    def _headers(self, settings: Settings) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key.strip()}",
            "User-Agent": f"ingest2md/{__version__}",
        }
        # Preserve the current Opencode Go behavior as a built-in configuration
        # detail while keeping the backend itself generic.
        if "opencode.ai" in settings.llm_base_url.lower():
            headers["x-opencode-session"] = self.session_id
        return headers

    def _post(self, settings: Settings, path: str, payload: dict, retries: int = 3) -> dict:
        last_error = None
        for attempt in range(retries):
            try:
                response = requests.post(
                    settings.llm_base_url.rstrip("/") + path,
                    json=payload,
                    headers=self._headers(settings),
                    timeout=600,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 < retries:
                    time.sleep(3 * (attempt + 1))
                    continue
                break
            if response.status_code != 200:
                raise RuntimeError(f"LLM audio HTTP {response.status_code}: {response.text[:500]}")
            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError("LLM audio 返回非 JSON 数据") from exc
            if not isinstance(data, dict):
                raise RuntimeError("LLM audio 返回非对象 JSON")
            return data
        raise RuntimeError(f"LLM audio 网络请求失败: {last_error}")

    def _chat(self, settings: Settings, model: str, audio_b64: str) -> str:
        data = self._post(settings, "/chat/completions", {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": TRANSCRIBE_PROMPT},
                    {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "mp3"}},
                ],
            }],
        })
        try:
            return self._extract_text(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"LLM audio chat 响应结构异常: {str(data)[:300]}") from exc

    def _responses(self, settings: Settings, model: str, audio_b64: str) -> str:
        data = self._post(settings, "/responses", {
            "model": model,
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": TRANSCRIBE_PROMPT},
                    {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "mp3"}},
                ],
            }],
        })
        text = data.get("output_text")
        if text is None:
            text = "\n".join(
                content.get("text", "")
                for item in data.get("output", [])
                for content in item.get("content", [])
                if content.get("type") in {"output_text", "text"}
            )
        text = self._extract_text(text)
        if not text:
            raise RuntimeError(f"LLM audio responses 响应结构异常: {str(data)[:300]}")
        return text

    def _transcribe_one(self, settings: Settings, path: str) -> str:
        with open(path, "rb") as stream:
            audio_b64 = base64.b64encode(stream.read()).decode()

        candidates = list(settings.llm_candidates)
        if not any(item["id"] == settings.llm_model for item in candidates):
            candidates.insert(0, {"id": settings.llm_model, "api": settings.llm_api})
        preferred = sorted(candidates, key=lambda item: item["id"] != settings.llm_model)
        order = (
            [self.working] + [item for item in preferred if item != self.working]
            if self.working else preferred
        )
        last_error = None
        for candidate in order:
            try:
                text = (
                    self._responses(settings, candidate["id"], audio_b64)
                    if candidate["api"] == "responses"
                    else self._chat(settings, candidate["id"], audio_b64)
                )
                if not text:
                    raise RuntimeError("模型返回空转写")
                self.working = candidate
                if candidate["id"] not in self.used_models:
                    self.used_models.append(candidate["id"])
                return text
            except RuntimeError as exc:
                last_error = exc
        raise RuntimeError(f"所有 LLM audio 候选模型均失败: {last_error}")

    def transcribe(self, audio_path: str, work_dir: Path, settings: Settings) -> TranscriptResult:
        if not settings.llm_api_key.strip():
            raise ValueError("LLM audio backend 未配置 API Key")
        if not settings.llm_model.strip():
            raise ValueError("llm_model 不能为空")

        chunks = chunk_audio_mp3(
            audio_path,
            settings.llm_chunk_seconds,
            settings.limit_seconds,
            work_dir / "chunks",
        )
        if not chunks:
            raise ValueError("音频过短或没有可转写内容")

        segments: list[Segment] = []
        for index, chunk in enumerate(chunks, 1):
            logger.info("LLM audio 转写 [%s/%s]", index, len(chunks))
            text = self._transcribe_one(settings, chunk["path"])
            if text and text != "[无语音]":
                segments.append(Segment(chunk["start"], chunk["end"], text))

        return TranscriptResult(
            segments=segments,
            models=self.used_models or [settings.llm_model],
            processed_seconds=chunks[-1]["end"],
            timestamp_precision="chunk",
            language=settings.asr_language,
        )
