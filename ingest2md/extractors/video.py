"""Shared media presentation helpers; v0.8 keeps source language unchanged."""
import shutil
from pathlib import Path

from ingest2md.config import Settings
from ingest2md.model import Document


def attach_video_description(doc: Document, description: str) -> None:
    doc.original_title = doc.title
    doc.original_description = description
    if description.strip():
        doc.body_md = "> 视频简介：" + description.replace("\n", " ") + "\n\n" + doc.body_md
    doc.metadata.append(("输出", "原语言内容（未翻译）"))


def retain_media(doc: Document, media_path: str, work: Path,
                 output_dir: Path, settings: Settings,
                 retained_filename: str | None = None) -> None:
    doc_dir = output_dir / doc.dirname
    if settings.keep_audio:
        doc_dir.mkdir(parents=True, exist_ok=True)
        filename = retained_filename or ("audio" + Path(media_path).suffix)
        shutil.copy2(media_path, doc_dir / filename)
        doc.attachments.append(filename)
    if settings.keep_chunks:
        for chunk in sorted((work / "chunks").glob("*")):
            if not chunk.is_file():
                continue
            target = doc_dir / "chunks" / chunk.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(chunk, target)
            doc.attachments.append(f"chunks/{chunk.name}")
