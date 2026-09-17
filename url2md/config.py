"""Explicit config loading; importing the package never reads credentials."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Settings:
    api_key: str = field(default="", repr=False)
    base_url: str = "https://opencode.ai/zen/go/v1"
    model: str = "mimo-v2.5"
    translation_model: str = ""  # Empty means use the transcription model.
    candidates: list[dict[str, str]] = field(default_factory=list)
    chunk_seconds: int = 300
    limit_seconds: int = 0
    cookies_file: str = ""  # Legacy shared fallback for all yt-dlp sites.
    youtube_cookies_file: str = ""
    bilibili_cookies_file: str = ""
    zhihu_cookies_file: str = ""
    xiaohongshu_cookies_file: str = ""
    max_answers: int = 0  # 0 = 尽可能多抓取知乎回答
    output_dir: str = "output"
    formats: tuple[str, ...] = ("md",)
    keep_audio: bool = False
    keep_chunks: bool = False


def load_settings(config_path: str | None = None, **overrides) -> Settings:
    # An explicit file is required to import legacy settings; no sibling lookup.
    path = Path(config_path).expanduser().resolve() if config_path else Path("config.yaml").resolve()
    data = {}
    if config_path or path.is_file():
        with path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
        if not isinstance(data, dict):
            raise ValueError("配置文件必须是键值映射")
    unknown = set(data) - set(Settings.__dataclass_fields__)
    if unknown:
        raise ValueError(f"未知配置项: {', '.join(sorted(map(str, unknown)))}")
    # Relative paths in a config file are relative to that file, not the CLI cwd.
    for key in ("cookies_file", "youtube_cookies_file", "bilibili_cookies_file", "zhihu_cookies_file", "xiaohongshu_cookies_file", "output_dir"):
        if data.get(key):
            value = Path(data[key]).expanduser()
            data[key] = str(value if value.is_absolute() else path.parent / value)
    if os.environ.get("OPENCODE_API_KEY"):
        data["api_key"] = os.environ["OPENCODE_API_KEY"]
    data.update({k: v for k, v in overrides.items() if v is not None})
    settings = Settings(**data)
    if type(settings.chunk_seconds) is not int or settings.chunk_seconds <= 0:
        raise ValueError("chunk_seconds 必须是正整数")
    if type(settings.limit_seconds) is not int or settings.limit_seconds < 0:
        raise ValueError("limit_seconds 必须是非负整数")
    if type(settings.max_answers) is not int or settings.max_answers < 0:
        raise ValueError("max_answers 必须是非负整数")
    formats = settings.formats
    if isinstance(formats, str):
        formats = [part.strip() for part in formats.split(",") if part.strip()]
    if not isinstance(formats, (list, tuple)) or not formats or any(f not in {"md", "txt", "srt", "json"} for f in formats):
        raise ValueError("formats 仅支持 md,txt,srt,json")
    # Markdown is always the primary archive; other formats are supplementary.
    settings.formats = tuple(dict.fromkeys(["md", *formats]))
    if not isinstance(settings.candidates, list) or any(
        not isinstance(c, dict) or not c.get("id") or c.get("api") not in {"chat", "responses"}
        for c in settings.candidates
    ):
        raise ValueError("candidates 必须包含 id 和 api(chat/responses)")
    for key in ("api_key", "base_url", "model", "translation_model", "cookies_file",
                "youtube_cookies_file", "bilibili_cookies_file", "zhihu_cookies_file",
                "xiaohongshu_cookies_file", "output_dir"):
        if not isinstance(getattr(settings, key), str):
            raise ValueError(f"{key} 必须是字符串")
    if not settings.model.strip():
        raise ValueError("model 不能为空")
    for key in ("keep_audio", "keep_chunks"):
        if type(getattr(settings, key)) is not bool:
            raise ValueError(f"{key} 必须是布尔值")
    return settings
