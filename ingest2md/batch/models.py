"""Lightweight batch task models and stable keys."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ingest2md.config import Settings
from ingest2md.router import normalize_reference


@dataclass(frozen=True)
class BatchItem:
    source: str
    name: str = ""
    tags: tuple[str, ...] = ()
    line_number: int = 0


@dataclass
class BatchSummary:
    total: int
    success: int
    failed: int
    pending: int
    running: int


_FINGERPRINT_FIELDS = (
    "asr_backend", "asr_language", "limit_seconds", "subtitle_window_seconds", "transcript_window_seconds",
    "sensevoice_model_dir", "sensevoice_chunk_seconds", "sensevoice_batch_size",
    "sensevoice_quantize", "openai_asr_base_url", "openai_asr_model",
    "openai_asr_chunk_seconds", "asr_prompt", "llm_base_url", "llm_model",
    "llm_api", "llm_chunk_seconds", "llm_candidates", "max_answers", "formats",
    "keep_audio", "keep_chunks",
)


def config_fingerprint(settings: Settings) -> str:
    """Hash only settings that materially affect generated artifacts."""
    payload = {key: getattr(settings, key) for key in _FINGERPRINT_FIELDS}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=list)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def task_identity(source: str) -> tuple[str, str]:
    """Return normalized input plus a stable pre-acquisition task key."""
    normalized = normalize_reference(source)
    path = Path(normalized).expanduser()
    if path.is_file():
        stat = path.stat()
        material = f"file:{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
    else:
        material = f"ref:{normalized}"
    key = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return normalized, key
