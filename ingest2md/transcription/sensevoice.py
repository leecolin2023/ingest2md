"""Local-first SenseVoiceSmall ONNX backend adapted from the user's proven offline transcriber."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ingest2md.config import Settings
from ingest2md.media.audio import chunk_audio_wav
from ingest2md.transcription.model import Segment, TranscriptResult

logger = logging.getLogger(__name__)
_TAG_RE = re.compile(r"<\|[^>]+?\|>")


def _import_runtime():
    try:
        from funasr_onnx import SenseVoiceSmall
    except ImportError as exc:
        raise ImportError(
            '本地转写需要 SenseVoice 依赖，请安装：python -m pip install "ingest2md[local-asr]"'
        ) from exc
    try:
        from funasr_onnx.utils.postprocess_utils import rich_transcription_postprocess
    except ImportError:
        rich_transcription_postprocess = None
    return SenseVoiceSmall, rich_transcription_postprocess


def _resolve_model_dir(settings: Settings) -> Path:
    if settings.sensevoice_model_dir:
        path = Path(settings.sensevoice_model_dir).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"SenseVoiceSmall 模型目录不存在: {path}")
        return path
    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise ImportError(
            '首次自动下载 SenseVoiceSmall 需要 modelscope；请安装：'
            'python -m pip install "ingest2md[local-asr]"'
        ) from exc
    logger.info("首次使用本地 ASR：下载/定位 SenseVoiceSmall 模型")
    return Path(snapshot_download("iic/SenseVoiceSmall")).resolve()


def _extract_text(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("text", "sentence", "value"):
            value = result.get(key)
            if isinstance(value, str):
                return value
        return " ".join(_extract_text(value) for value in result.values()).strip()
    if isinstance(result, (list, tuple)):
        return "\n".join(part for part in (_extract_text(item) for item in result) if part).strip()
    return str(result or "").strip()


def _clean_text(text: str, postprocess=None) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    if postprocess:
        try:
            return str(postprocess(text)).strip()
        except Exception:
            pass
    return _TAG_RE.sub("", text).strip()


class SenseVoiceBackend:
    name = "sensevoice"

    @staticmethod
    def _run_model(model, audio_path: str, language: str, use_itn: bool = True):
        attempts = [
            lambda: model([audio_path], language=language, use_itn=use_itn),
            lambda: model(audio_path, language=language, use_itn=use_itn),
        ]
        generate = getattr(model, "generate", None)
        if generate:
            attempts.extend([
                lambda: generate(input=[audio_path], language=language, use_itn=use_itn),
                lambda: generate(input=audio_path, language=language, use_itn=use_itn),
                lambda: generate([audio_path], language=language, use_itn=use_itn),
                lambda: generate(audio_path, language=language, use_itn=use_itn),
            ])
        last_error = None
        for attempt in attempts:
            try:
                return attempt()
            except TypeError as exc:
                last_error = exc
        if last_error:
            raise last_error
        raise RuntimeError("SenseVoiceSmall ONNX 调用失败")

    def transcribe(self, audio_path: str, work_dir: Path, settings: Settings) -> TranscriptResult:
        chunks = chunk_audio_wav(
            audio_path,
            settings.sensevoice_chunk_seconds,
            settings.limit_seconds,
            work_dir / "chunks",
        )
        if not chunks:
            raise ValueError("音频过短或没有可转写内容")

        model_dir = _resolve_model_dir(settings)
        SenseVoiceSmall, postprocess = _import_runtime()
        logger.info(
            "加载本地 SenseVoiceSmall ONNX: %s (batch=%s, quantize=%s)",
            model_dir, settings.sensevoice_batch_size, settings.sensevoice_quantize,
        )
        model = SenseVoiceSmall(
            str(model_dir),
            batch_size=settings.sensevoice_batch_size,
            quantize=settings.sensevoice_quantize,
        )

        segments: list[Segment] = []
        for index, chunk in enumerate(chunks, 1):
            logger.info("SenseVoice 本地转写 [%s/%s]", index, len(chunks))
            result = self._run_model(model, chunk["path"], settings.asr_language)
            text = _clean_text(_extract_text(result), postprocess)
            if text:
                segments.append(Segment(chunk["start"], chunk["end"], text))

        return TranscriptResult(
            segments=segments,
            models=["sensevoice-onnx:SenseVoiceSmall"],
            processed_seconds=chunks[-1]["end"],
            timestamp_precision="chunk",
            language=settings.asr_language,
        )
