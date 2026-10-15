"""OpenAI-compatible /audio/transcriptions backend."""
from __future__ import annotations

import logging
from pathlib import Path

import requests

from ingest2md.config import Settings
from ingest2md.media.audio import chunk_audio_mp3
from ingest2md.transcription.model import Segment, TranscriptResult

logger = logging.getLogger(__name__)


def _transcription_url(base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        raise ValueError("openai_asr_base_url 不能为空")
    return url if url.endswith("/audio/transcriptions") else url + "/audio/transcriptions"


class OpenAIASRBackend:
    name = "openai"

    def transcribe(self, audio_path: str, work_dir: Path, settings: Settings) -> TranscriptResult:
        if not settings.openai_asr_api_key.strip():
            raise ValueError("OpenAI-compatible ASR 未配置 API Key")
        if not settings.openai_asr_model.strip():
            raise ValueError("openai_asr_model 不能为空")

        chunks = chunk_audio_mp3(
            audio_path,
            settings.openai_asr_chunk_seconds,
            settings.limit_seconds,
            work_dir / "chunks",
        )
        if not chunks:
            raise ValueError("音频过短或没有可转写内容")

        segments: list[Segment] = []
        url = _transcription_url(settings.openai_asr_base_url)
        for index, chunk in enumerate(chunks, 1):
            logger.info("OpenAI-compatible ASR [%s/%s]", index, len(chunks))
            data = {
                "model": settings.openai_asr_model,
                "response_format": "json",
            }
            if settings.asr_language.lower() != "auto":
                data["language"] = settings.asr_language
            if settings.asr_prompt.strip():
                data["prompt"] = settings.asr_prompt
            with open(chunk["path"], "rb") as stream:
                response = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {settings.openai_asr_api_key.strip()}"},
                    data=data,
                    files={"file": (Path(chunk["path"]).name, stream, "audio/mpeg")},
                    timeout=settings.openai_asr_timeout,
                )
            if response.status_code != 200:
                raise RuntimeError(
                    f"OpenAI-compatible ASR HTTP {response.status_code}: {response.text[:500]}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError("OpenAI-compatible ASR 返回非 JSON 数据") from exc
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                returned = payload.get("segments")
                if isinstance(returned, list):
                    text = " ".join(
                        str(item.get("text", "")).strip()
                        for item in returned if isinstance(item, dict)
                    )
            if not isinstance(text, str) or not text.strip():
                raise RuntimeError("OpenAI-compatible ASR 返回结果中没有 text")
            segments.append(Segment(chunk["start"], chunk["end"], text.strip()))

        return TranscriptResult(
            segments=segments,
            models=[settings.openai_asr_model],
            processed_seconds=chunks[-1]["end"],
            timestamp_precision="chunk",
            language=settings.asr_language,
        )
