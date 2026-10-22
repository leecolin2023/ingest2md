"""Shared lightweight data model and output writer."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from filelock import FileLock

from ingest2md.transcription.model import TranscriptResult

_UNSAFE_FILENAME_CHARS = re.compile(r'[/\\?%*:|"<>\x00-\x1f]')


def sanitize_filename(name: str, max_length: int = 80) -> str:
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", name).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned.strip("_ "):
        cleaned = "untitled"
    return cleaned[:max_length]


# The primary Markdown filename, including ".md", has a 150-byte UTF-8 budget.
MAX_OUTPUT_FILENAME_BYTES = 150
_CHINA_TZ = timezone(timedelta(hours=8))
_DATED_STEM_RE = re.compile(r"^\\d{8}__(.+)$")


def _safe_output_title(title: str, max_bytes: int) -> str:
    """Shorten a sanitized title without cutting a UTF-8 character."""
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", title)
    cleaned = re.sub(r"\\s+", " ", cleaned).strip().strip(".")
    if not cleaned.strip("_ "):
        cleaned = "untitled"
    length = 0
    chars: list[str] = []
    for char in cleaned:
        size = len(char.encode("utf-8"))
        if length + size > max_bytes:
            break
        chars.append(char)
        length += size
    return "".join(chars).rstrip(" .") or "untitled"


@dataclass
class Document:
    """One user-facing content object rendered primarily as Markdown."""

    title: str
    source_url: str
    metadata: list[tuple[str, str]] = field(default_factory=list)
    body_md: str = ""
    image_map: dict[str, str] = field(default_factory=dict)
    publish_time: datetime | None = None
    captured_at: datetime = field(default_factory=lambda: datetime.now(_CHINA_TZ))
    source_id: str = ""
    source_type: str = ""
    transcript: TranscriptResult | None = None
    attachments: list[str] = field(default_factory=list)
    original_title: str = ""
    original_description: str = ""

    @property
    def dirname(self) -> str:
        """Date + title only; source ID and time-of-day are intentionally omitted."""
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at 必须带时区")
        prefix = self.captured_at.astimezone(_CHINA_TZ).strftime("%Y%m%d") + "__"
        budget = MAX_OUTPUT_FILENAME_BYTES - len(prefix.encode("utf-8")) - len(".md")
        return prefix + _safe_output_title(self.title, budget)

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
        "captured_at": doc.captured_at.isoformat(),
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
        md_path = doc_dir / "content.md"
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


def publish_document(
    doc: Document,
    staged_md: Path,
    staging_dir: Path,
    output_dir: Path,
) -> Path:
    """Atomically publish staged output, replacing previous dates for an exact title.

    An adapter must finish all attachments inside the staging directory before
    publication. Under the cross-process lock, the old output is moved aside
    and restored if the final move fails.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    staged_entry = staged_md if staged_md.parent == staging_dir else staged_md.parent
    target_entry = output_dir / staged_entry.name

    with FileLock(str(output_dir / ".ingest2md-output.lock"), timeout=30):
        previous_entries: list[Path] = []
        title_suffix = doc.dirname[10:]
        for candidate in output_dir.iterdir():
            if candidate.is_file() and candidate.suffix == ".md":
                candidate_stem, candidate_md = candidate.stem, candidate
            elif candidate.is_dir():
                candidate_stem, candidate_md = candidate.name, candidate / "content.md"
            else:
                continue
            match = _DATED_STEM_RE.fullmatch(candidate_stem)
            if not match or match.group(1) != title_suffix:
                continue
            if candidate_md.is_file():
                with candidate_md.open(encoding="utf-8") as stream:
                    saved_heading = stream.readline().rstrip("\r\n")
                if saved_heading == f"# {doc.title}":
                    previous_entries.append(candidate)
                    continue
            # Different full titles can truncate to the same 150-byte stem.
            # They must never overwrite each other.
            if candidate == target_entry:
                raise FileExistsError(
                    f"标题截断后产物重名，拒绝覆盖: {candidate.name}；"
                    "请修改标题或使用另一输出目录"
                )

        if target_entry.exists() and target_entry not in previous_entries:
            raise FileExistsError(f"产物路径已被其他内容占用: {target_entry}")

        backup_dir = Path(tempfile.mkdtemp(prefix=".ingest2md-replace-", dir=output_dir))
        moved: list[Path] = []
        committed = False
        try:
            for old_entry in previous_entries:
                os.replace(old_entry, backup_dir / old_entry.name)
                moved.append(old_entry)
            os.replace(staged_entry, target_entry)
            committed = True
        finally:
            if not committed:
                for old_entry in reversed(moved):
                    os.replace(backup_dir / old_entry.name, old_entry)
            if committed:
                # Failed removal of obsolete backups must not mark the newly
                # published document as failed.
                shutil.rmtree(backup_dir, ignore_errors=True)
            else:
                try:
                    backup_dir.rmdir()
                except OSError:
                    pass

    return target_entry / "content.md" if target_entry.is_dir() else target_entry
