"""Core single-item ingestion service shared by CLI, batch, and future APIs."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ingest2md.config import Settings
from ingest2md.extractors.base import SourceUnavailableError
from ingest2md.model import Document, write_document
from ingest2md.router import UnsupportedURLError, find_extractor, normalize_reference

if TYPE_CHECKING:
    from ingest2md.runtime import RuntimeContext


@dataclass(frozen=True)
class IngestionRequest:
    source: str
    name: str = ""
    tags: tuple[str, ...] = ()


@dataclass
class IngestionResult:
    raw_source: str
    reference: str = ""
    source_type: str = ""
    source_id: str = ""
    canonical_key: str = ""
    status: str = "failed"
    output_path: Path | None = None
    error_code: str = ""
    error_message: str = ""
    retryable: bool = False
    document: Document | None = field(default=None, repr=False)
    exception: Exception | None = field(default=None, repr=False)


_RESULT_CONFIG_KEYS = (
    "asr_backend", "asr_language", "limit_seconds", "subtitle_window_seconds",
    "sensevoice_model_dir", "sensevoice_chunk_seconds", "sensevoice_batch_size",
    "sensevoice_quantize", "openai_asr_base_url", "openai_asr_model",
    "openai_asr_chunk_seconds", "asr_prompt", "llm_base_url", "llm_model",
    "llm_api", "llm_chunk_seconds", "llm_candidates", "max_answers", "formats",
    "keep_audio", "keep_chunks",
)
_COOKIE_KEYS = (
    "cookies_file", "youtube_cookies_file", "bilibili_cookies_file",
    "zhihu_cookies_file", "xiaohongshu_cookies_file", "douyin_cookies_file",
)


def config_fingerprint(settings: Settings) -> str:
    """Fingerprint result-affecting settings without persisting credentials."""
    payload = {key: getattr(settings, key) for key in _RESULT_CONFIG_KEYS}
    cookie_state = {}
    for key in _COOKIE_KEYS:
        value = getattr(settings, key)
        if not value:
            continue
        path = Path(value).expanduser()
        try:
            stat = path.stat()
            cookie_state[key] = {
                "path": str(path.resolve()),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        except OSError:
            cookie_state[key] = {"path": str(path)}
    payload["cookie_state"] = cookie_state
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def task_identity(source: str) -> tuple[str, str]:
    """Return normalized source and a stable pre-ingestion task key."""
    try:
        reference = normalize_reference(source)
    except Exception:
        reference = (source or "").strip()
    path = Path(reference).expanduser()
    try:
        if path.is_file():
            resolved = path.resolve()
            stat = resolved.stat()
            basis = f"file|{resolved}|{stat.st_size}|{stat.st_mtime_ns}"
            return str(resolved), hashlib.sha256(basis.encode("utf-8")).hexdigest()
    except (OSError, ValueError):
        pass
    basis = "ref|" + reference
    return reference, hashlib.sha256(basis.encode("utf-8")).hexdigest()


def classify_error(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, (UnsupportedURLError, SourceUnavailableError)):
        return "unsupported", False
    if isinstance(exc, ImportError):
        return "missing_dependency", False
    text = str(exc).lower()
    if any(token in text for token in ("429", "timeout", "timed out", "temporarily", "502", "503", "504")):
        return "transient_network", True
    if any(token in text for token in ("cookie", "登录", "login", "auth", "验证码")):
        return "auth_required", False
    if any(token in text for token in ("无音轨", "invalid media", "媒体候选", "media candidate")):
        return "invalid_media", False
    if "asr" in text or "转写" in text:
        return "transcription_failed", False
    return "ingestion_failed", False


class IngestionEngine:
    """One platform-neutral ingestion path used by both single and batch modes."""

    def __init__(self, settings: Settings, output_dir: Path,
                 runtime: "RuntimeContext | None" = None):
        self.settings = settings
        self.output_dir = Path(output_dir)
        self.runtime = runtime

    async def ingest_one(self, request: IngestionRequest) -> IngestionResult:
        raw_source = request.source
        reference = ""
        try:
            reference = normalize_reference(raw_source)
            extractor = find_extractor(
                reference,
                settings=self.settings,
                runtime=self.runtime,
            )
            doc = await extractor.extract(reference, self.output_dir)
            output_path = write_document(doc, self.output_dir, self.settings.formats)
            canonical_key = (
                f"{doc.source_type}:{doc.source_id}"
                if doc.source_type and doc.source_id
                else f"{doc.source_type or 'content'}:{doc.source_url or reference}"
            )
            return IngestionResult(
                raw_source=raw_source,
                reference=reference,
                source_type=doc.source_type,
                source_id=doc.source_id,
                canonical_key=canonical_key,
                status="success",
                output_path=output_path,
                document=doc,
            )
        except Exception as exc:
            code, retryable = classify_error(exc)
            return IngestionResult(
                raw_source=raw_source,
                reference=reference,
                status="failed",
                error_code=code,
                error_message=str(exc),
                retryable=retryable,
                exception=exc,
            )
