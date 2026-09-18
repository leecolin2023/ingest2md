"""Explicit config loading; importing the package never reads credentials."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Settings:
    # ASR routing. Local SenseVoice is the product default; paid/cloud APIs are opt-in.
    asr_backend: str = "sensevoice"  # sensevoice | openai | llm
    asr_language: str = "auto"
    limit_seconds: int = 0
    subtitle_window_seconds: int = 300

    # Local SenseVoice ONNX.
    sensevoice_model_dir: str = ""
    sensevoice_chunk_seconds: int = 20
    sensevoice_batch_size: int = 1
    sensevoice_quantize: bool = True

    # OpenAI-compatible /audio/transcriptions.
    openai_asr_base_url: str = "https://api.openai.com/v1"
    openai_asr_api_key: str = field(default="", repr=False)
    openai_asr_model: str = "gpt-4o-transcribe"
    openai_asr_chunk_seconds: int = 1200
    openai_asr_timeout: int = 600
    asr_prompt: str = ""

    # Generic multimodal LLM audio endpoint. Opencode is only the default example config.
    llm_base_url: str = "https://opencode.ai/zen/go/v1"
    llm_api_key: str = field(default="", repr=False)
    llm_model: str = "mimo-v2.5"
    llm_api: str = "chat"  # chat | responses
    llm_chunk_seconds: int = 300
    llm_candidates: list[dict[str, str]] = field(default_factory=list)

    cookies_file: str = ""
    youtube_cookies_file: str = ""
    bilibili_cookies_file: str = ""
    zhihu_cookies_file: str = ""
    xiaohongshu_cookies_file: str = ""
    max_answers: int = 0
    output_dir: str = "output"
    formats: tuple[str, ...] = ("md",)
    keep_audio: bool = False
    keep_chunks: bool = False


def _migrate_legacy_config(data: dict) -> dict:
    """Keep v0.7 config files readable while moving cloud settings under explicit names."""
    data = dict(data)
    aliases = {
        "api_key": "llm_api_key",
        "base_url": "llm_base_url",
        "model": "llm_model",
        "candidates": "llm_candidates",
    }
    for old, new in aliases.items():
        if old in data and new not in data:
            data[new] = data[old]
        data.pop(old, None)
    # Translation was intentionally removed in v0.8.
    data.pop("translation_model", None)
    if "chunk_seconds" in data:
        value = data.pop("chunk_seconds")
        data.setdefault("llm_chunk_seconds", value)
        data.setdefault("subtitle_window_seconds", value)
    return data


def load_settings(config_path: str | None = None, **overrides) -> Settings:
    path = Path(config_path).expanduser().resolve() if config_path else Path("config.yaml").resolve()
    data = {}
    if config_path or path.is_file():
        with path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
        if not isinstance(data, dict):
            raise ValueError("配置文件必须是键值映射")
        data = _migrate_legacy_config(data)

    unknown = set(data) - set(Settings.__dataclass_fields__)
    if unknown:
        raise ValueError(f"未知配置项: {', '.join(sorted(map(str, unknown)))}")

    for key in (
        "cookies_file", "youtube_cookies_file", "bilibili_cookies_file",
        "zhihu_cookies_file", "xiaohongshu_cookies_file", "output_dir",
        "sensevoice_model_dir",
    ):
        if data.get(key):
            value = Path(data[key]).expanduser()
            data[key] = str(value if value.is_absolute() else path.parent / value)

    # Environment variables configure optional cloud backends but never switch away
    # from the local default automatically.
    if os.environ.get("ASR_BACKEND"):
        data["asr_backend"] = os.environ["ASR_BACKEND"]
    if os.environ.get("ASR_LANGUAGE"):
        data["asr_language"] = os.environ["ASR_LANGUAGE"]
    if os.environ.get("ASR_API_KEY"):
        data["openai_asr_api_key"] = os.environ["ASR_API_KEY"]
    elif os.environ.get("OPENAI_API_KEY"):
        data["openai_asr_api_key"] = os.environ["OPENAI_API_KEY"]
    if os.environ.get("ASR_API_BASE_URL"):
        data["openai_asr_base_url"] = os.environ["ASR_API_BASE_URL"]
    if os.environ.get("ASR_MODEL"):
        data["openai_asr_model"] = os.environ["ASR_MODEL"]
    if os.environ.get("OPENCODE_API_KEY"):
        data["llm_api_key"] = os.environ["OPENCODE_API_KEY"]

    data.update({k: v for k, v in overrides.items() if v is not None})
    settings = Settings(**data)

    if settings.asr_backend not in {"sensevoice", "openai", "llm"}:
        raise ValueError("asr_backend 仅支持 sensevoice, openai, llm")
    if not isinstance(settings.asr_language, str) or not settings.asr_language.strip():
        raise ValueError("asr_language 必须是非空字符串")
    if type(settings.limit_seconds) is not int or settings.limit_seconds < 0:
        raise ValueError("limit_seconds 必须是非负整数")
    if type(settings.max_answers) is not int or settings.max_answers < 0:
        raise ValueError("max_answers 必须是非负整数")

    for key in (
        "subtitle_window_seconds", "sensevoice_chunk_seconds", "sensevoice_batch_size",
        "openai_asr_chunk_seconds", "openai_asr_timeout", "llm_chunk_seconds",
    ):
        if type(getattr(settings, key)) is not int or getattr(settings, key) <= 0:
            raise ValueError(f"{key} 必须是正整数")

    if not 5 <= settings.sensevoice_chunk_seconds <= 30:
        raise ValueError("sensevoice_chunk_seconds 必须在 5–30 秒之间")
    if settings.llm_api not in {"chat", "responses"}:
        raise ValueError("llm_api 仅支持 chat 或 responses")
    if not isinstance(settings.llm_candidates, list) or any(
        not isinstance(c, dict) or not c.get("id") or c.get("api") not in {"chat", "responses"}
        for c in settings.llm_candidates
    ):
        raise ValueError("llm_candidates 必须包含 id 和 api(chat/responses)")

    formats = settings.formats
    if isinstance(formats, str):
        formats = [part.strip() for part in formats.split(",") if part.strip()]
    if not isinstance(formats, (list, tuple)) or not formats or any(
        f not in {"md", "txt", "srt", "json"} for f in formats
    ):
        raise ValueError("formats 仅支持 md,txt,srt,json")
    settings.formats = tuple(dict.fromkeys(["md", *formats]))

    for key in (
        "asr_backend", "asr_language", "sensevoice_model_dir",
        "openai_asr_base_url", "openai_asr_api_key", "openai_asr_model", "asr_prompt",
        "llm_base_url", "llm_api_key", "llm_model", "llm_api",
        "cookies_file", "youtube_cookies_file", "bilibili_cookies_file",
        "zhihu_cookies_file", "xiaohongshu_cookies_file", "output_dir",
    ):
        if not isinstance(getattr(settings, key), str):
            raise ValueError(f"{key} 必须是字符串")

    for key in ("sensevoice_quantize", "keep_audio", "keep_chunks"):
        if type(getattr(settings, key)) is not bool:
            raise ValueError(f"{key} 必须是布尔值")
    return settings
