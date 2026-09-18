"""Chinese translation shared by every video source."""
from typing import Protocol

from ingest2md.config import Settings
from ingest2md.transcription.opencode import OpencodeEngine


class Translator(Protocol):
    def translate(self, text: str) -> str: ...


def make_translator(settings: Settings) -> OpencodeEngine:
    return OpencodeEngine(settings.api_key, settings.base_url,
                          settings.translation_model or settings.model, settings.candidates)


def translate_text(text: str, translator: Translator, max_chars: int = 4000) -> str:
    """Bound text requests; split near paragraph/sentence boundaries when possible."""
    if max_chars <= 0:
        raise ValueError("max_chars 必须大于零")
    parts = []
    while text:
        end = min(len(text), max_chars)
        if end < len(text):
            boundary = max(text.rfind(mark, 0, end) for mark in ("\n", ". ", "。", "! ", "? ", " "))
            if boundary >= end // 2:
                end = boundary + 1
        part, text = text[:end], text[end:]
        if part.strip():
            translated = translator.translate(part)
            if not isinstance(translated, str) or not translated.strip():
                raise ValueError("翻译返回空文本，任务未完成")
            parts.append(translated.strip())
    return "\n\n".join(parts)
