"""Local-first SenseVoiceSmall ONNX backend with batched CPU inference."""
from __future__ import annotations

import logging
import math
import re
import time
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


def _batch_items(result, expected: int) -> list:
    """Preserve one result per input path; never silently merge batch outputs."""
    if expected == 1:
        if isinstance(result, (list, tuple)) and len(result) == 1:
            return [result[0]]
        return [result]
    if isinstance(result, (list, tuple)) and len(result) == expected:
        return list(result)
    raise RuntimeError(
        f"SenseVoice 批量返回数量异常：输入 {expected} 段，返回 "
        f"{len(result) if isinstance(result, (list, tuple)) else type(result).__name__}"
    )


class SenseVoiceBackend:
    name = "sensevoice"

    @staticmethod
    def _run_model(model, audio_paths: list[str], language: str, use_itn: bool = True):
        """Prefer true list input; retain single-file fallbacks for older runtimes."""
        paths = list(audio_paths)
        attempts = [
            lambda: model(paths, language=language, use_itn=use_itn),
        ]
        generate = getattr(model, "generate", None)
        if generate:
            attempts.extend([
                lambda: generate(input=paths, language=language, use_itn=use_itn),
                lambda: generate(paths, language=language, use_itn=use_itn),
            ])
        if len(paths) == 1:
            path = paths[0]
            attempts.extend([
                lambda: model(path, language=language, use_itn=use_itn),
            ])
            if generate:
                attempts.extend([
                    lambda: generate(input=path, language=language, use_itn=use_itn),
                    lambda: generate(path, language=language, use_itn=use_itn),
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
        total_started = time.perf_counter()

        preprocess_started = time.perf_counter()
        chunks = chunk_audio_wav(
            audio_path,
            settings.sensevoice_chunk_seconds,
            settings.limit_seconds,
            work_dir / "chunks",
        )
        preprocess_seconds = time.perf_counter() - preprocess_started
        if not chunks:
            raise ValueError("音频过短或没有可转写内容")

        setup_started = time.perf_counter()
        model_dir = _resolve_model_dir(settings)
        SenseVoiceSmall, postprocess = _import_runtime()
        logger.info(
            "加载本地 SenseVoiceSmall ONNX: %s (chunk=%ss, batch=%s, quantize=%s)",
            model_dir, settings.sensevoice_chunk_seconds,
            settings.sensevoice_batch_size, settings.sensevoice_quantize,
        )
        model = SenseVoiceSmall(
            str(model_dir),
            batch_size=settings.sensevoice_batch_size,
            quantize=settings.sensevoice_quantize,
        )
        setup_seconds = time.perf_counter() - setup_started

        batch_size = max(1, settings.sensevoice_batch_size)
        batch_count = math.ceil(len(chunks) / batch_size)
        segments: list[Segment] = []

        inference_started = time.perf_counter()
        model_calls = 0
        for batch_index, offset in enumerate(range(0, len(chunks), batch_size), 1):
            batch = chunks[offset:offset + batch_size]
            paths = [chunk["path"] for chunk in batch]
            logger.info(
                "SenseVoice 本地转写 batch [%s/%s] chunks %s-%s/%s",
                batch_index, batch_count, offset + 1, offset + len(batch), len(chunks),
            )
            result = self._run_model(model, paths, settings.asr_language)
            model_calls += 1
            items = _batch_items(result, len(batch))
            for chunk, item in zip(batch, items):
                text = _clean_text(_extract_text(item), postprocess)
                if text:
                    segments.append(Segment(chunk["start"], chunk["end"], text))
        inference_seconds = time.perf_counter() - inference_started

        processed_seconds = chunks[-1]["end"]
        total_seconds = time.perf_counter() - total_started
        speed = processed_seconds / inference_seconds if inference_seconds > 0 else 0.0
        rtf = inference_seconds / processed_seconds if processed_seconds > 0 else 0.0
        logger.info(
            "SenseVoice 性能 | 预处理 %.1fs | 模型准备 %.1fs | 推理 %.1fs | 总计 %.1fs | "
            "音频 %.1fs | chunks=%s | batch=%s | model_calls=%s | %.1fx realtime | RTF=%.3f",
            preprocess_seconds, setup_seconds, inference_seconds, total_seconds,
            processed_seconds, len(chunks), batch_size, model_calls, speed, rtf,
        )

        return TranscriptResult(
            segments=segments,
            models=["sensevoice-onnx:SenseVoiceSmall"],
            processed_seconds=processed_seconds,
            timestamp_precision="chunk",
            language=settings.asr_language,
        )
