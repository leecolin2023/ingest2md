"""Deterministic and optional smart transcript normalization."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ingest2md.config import Settings
from ingest2md.transcription.model import NormalizationReport, Segment, TranscriptResult

_SPELLED_LATIN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z](?:\s+|[.·、]\s*)){1,7}[A-Za-z](?![A-Za-z0-9])"
)
_CJK_SPACE_RE = re.compile(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])")
_BEFORE_PUNCT_RE = re.compile(r"\s+([，。！？；：、,.!?;:])")
_AFTER_OPEN_RE = re.compile(r"([（(【\[])\s+")
_BEFORE_CLOSE_RE = re.compile(r"\s+([）)】\]])")
_DECORATIVE_ASR_RE = re.compile(r"[🎼😊😄😁😂😅😆😢😭😔😞😡😠😱😰😨🤢🤧😷🤒🤕]+")


@dataclass(frozen=True)
class NormalizationHints:
    """Source-provided context that improves normalization without platform coupling."""

    source_type: str = ""
    title: str = ""
    context: str = ""
    terms: tuple[str, ...] = ()
    people: tuple[str, ...] = ()

    @property
    def hint_count(self) -> int:
        values = [self.title, self.context, *self.terms, *self.people]
        return sum(1 for value in values if str(value or "").strip())

    def compact_context(self, limit: int = 4000) -> str:
        parts = []
        if self.title:
            parts.append(f"标题：{self.title}")
        if self.people:
            parts.append("人物：" + "、".join(self.people))
        if self.terms:
            parts.append("术语：" + "、".join(self.terms))
        if self.context:
            parts.append(self.context)
        return "\n".join(parts)[:limit]


def _merge_spelled_latin(match: re.Match[str]) -> str:
    letters = re.findall(r"[A-Za-z]", match.group(0))
    if 2 <= len(letters) <= 8:
        return "".join(letters).upper()
    return match.group(0)


def _canonicalize_terms(text: str, hints: NormalizationHints | None) -> str:
    if not hints:
        return text
    canonical = []
    for value in (*hints.terms, *hints.people):
        value = str(value or "").strip()
        if value and value not in canonical:
            canonical.append(value)
    for term in sorted(canonical, key=len, reverse=True):
        if not re.search(r"[A-Za-z]", term):
            continue
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])",
            re.I,
        )
        text = pattern.sub(term, text)
    return text


def basic_normalize_text(text: str, hints: NormalizationHints | None = None) -> str:
    """Apply local deterministic cleanup without inventing or paraphrasing content."""
    text = str(text or "").replace("\u00a0", " ").strip()
    if not text:
        return ""
    text = _DECORATIVE_ASR_RE.sub("", text)
    text = re.sub(r"[\t\r\n ]+", " ", text)
    text = _SPELLED_LATIN_RE.sub(_merge_spelled_latin, text)
    text = _CJK_SPACE_RE.sub("", text)
    text = _BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _AFTER_OPEN_RE.sub(r"\1", text)
    text = _BEFORE_CLOSE_RE.sub(r"\1", text)
    text = _canonicalize_terms(text, hints)
    return text.strip()


def _copy_result(
    result: TranscriptResult,
    segments: list[Segment],
    report: NormalizationReport,
) -> TranscriptResult:
    return TranscriptResult(
        segments=segments,
        models=list(result.models),
        processed_seconds=result.processed_seconds,
        timestamp_precision=result.timestamp_precision,
        language=result.language,
        normalization=report,
    )


def normalize_transcript(
    result: TranscriptResult,
    settings: Settings,
    hints: NormalizationHints | None = None,
) -> TranscriptResult:
    """Normalize ASR text while preserving segment count/order/timestamps."""
    mode = settings.transcript_normalization
    if mode == "off":
        return _copy_result(
            result,
            [
                Segment(
                    segment.start,
                    segment.end,
                    segment.text,
                    raw_text=segment.raw_text,
                )
                for segment in result.segments
            ],
            NormalizationReport(
                mode="off",
                processed_segments=len(result.segments),
                changed_segments=0,
                hints_used=0,
            ),
        )

    basic_segments = []
    for segment in result.segments:
        raw_text = segment.raw_text or segment.text
        basic_segments.append(
            Segment(
                segment.start,
                segment.end,
                basic_normalize_text(segment.text, hints),
                raw_text=raw_text,
            )
        )

    final_segments = basic_segments
    model = ""
    warnings: list[str] = []

    if mode == "llm":
        try:
            from ingest2md.transcription.normalization_llm import normalize_segments_with_llm

            normalized_texts, model, llm_warnings = normalize_segments_with_llm(
                basic_segments,
                hints or NormalizationHints(),
                settings,
            )
            warnings.extend(llm_warnings)
            if len(normalized_texts) != len(basic_segments):
                raise RuntimeError("LLM normalization 返回 segment 数量与输入不一致")
            final_segments = [
                Segment(
                    segment.start,
                    segment.end,
                    normalized_texts[index],
                    raw_text=segment.raw_text,
                )
                for index, segment in enumerate(basic_segments)
            ]
        except Exception as exc:
            warnings.append(f"LLM normalization 回退 basic: {exc}")
            final_segments = basic_segments

    changed = sum(
        1
        for raw, normalized in zip(result.segments, final_segments)
        if (raw.raw_text or raw.text).strip() != normalized.text.strip()
    )
    return _copy_result(
        result,
        final_segments,
        NormalizationReport(
            mode=mode,
            model=model,
            processed_segments=len(final_segments),
            changed_segments=changed,
            hints_used=(hints.hint_count if hints else 0),
            warnings=warnings,
        ),
    )
