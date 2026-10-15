"""Shared lightweight data model and output writer."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from ingest2md.transcription.model import TranscriptResult

_UNSAFE_FILENAME_CHARS = re.compile(r'[/\\?%*:|"<>\x00-\x1f]')


def sanitize_filename(name: str, max_length: int = 80) -> str:
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", name).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned.strip("_ "):
        cleaned = "untitled"
    return cleaned[:max_length]


@dataclass
class Document:
    """One user-facing content object rendered primarily as Markdown."""

    title: str
    source_url: str
    metadata: list[tuple[str, str]] = field(default_factory=list)
    body_md: str = ""
    image_map: dict[str, str] = field(default_factory=dict)
    publish_time: datetime | None = None
    source_id: str = ""
    source_type: str = ""
    transcript: TranscriptResult | None = None
    attachments: list[str] = field(default_factory=list)
    original_title: str = ""
    original_description: str = ""

    @property
    def dirname(self) -> str:
        title = sanitize_filename(self.title)
        return f"{title}__{sanitize_filename(self.source_id)}" if self.source_id else title

    def build_markdown(self) -> str:
        header = [f"# {self.title}"]
        if self.metadata:
            header.extend(f"> **{k}**: {v}" for k, v in self.metadata if v)
            header.append(">")
        header.append(f"> 原文链接: {self.source_url}")
        return "\n".join(header) + "\n\n---\n\n" + self.body_md.strip() + "\n"


def _record_for_json(doc: Document) -> dict:
    record = {
        "source_url": doc.source_url,
        "source_id": doc.source_id,
        "source_type": doc.source_type,
        "title": doc.title,
        "metadata": doc.metadata,
        "body_md": doc.body_md,
        "attachments": doc.attachments,
        "original_title": doc.original_title,
        "original_description": doc.original_description,
    }
    if doc.transcript:
        record["transcript"] = asdict(doc.transcript)
    return record


def write_document(doc: Document, output_dir: Path, formats=("md",)) -> Path:
    """Write one primary Markdown; supplementary formats are explicit opt-in.

    Text-only Markdown stays flat under output/. If local assets or requested
    extra formats exist, related files are grouped under one content directory.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    formats = tuple(dict.fromkeys(("md", *formats)))
    extra = set(formats) - {"md"}
    grouped = bool(doc.image_map or doc.attachments or extra)

    if grouped:
        doc_dir = output_dir / doc.dirname
        doc_dir.mkdir(parents=True, exist_ok=True)
        md_path = doc_dir / f"{doc.dirname}.md"
    else:
        doc_dir = output_dir
        md_path = output_dir / f"{doc.dirname}.md"
    md_path.write_text(doc.build_markdown(), encoding="utf-8")

    if "txt" in formats:
        text = doc.transcript.text if doc.transcript else doc.body_md
        (doc_dir / "transcript.txt").write_text(text.rstrip() + "\n", encoding="utf-8")
    if "json" in formats:
        (doc_dir / "document.json").write_text(
            json.dumps(_record_for_json(doc), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if "srt" in formats and doc.transcript:
        from ingest2md.transcription.writers import render_srt
        (doc_dir / "transcript.srt").write_text(render_srt(doc.transcript), encoding="utf-8")
    return md_path
