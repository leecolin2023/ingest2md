"""Shared Chinese video-document presentation and media retention."""
import shutil
from pathlib import Path

from url2md.config import Settings
from url2md.model import Document
from url2md.transcription.translation import make_translator, translate_text


def localize_metadata(doc: Document, description: str, settings: Settings) -> None:
    translator = make_translator(settings)
    doc.original_title = doc.title
    doc.original_description = description
    doc.title = translate_text(doc.title, translator).replace("\n", " ")
    if description.strip():
        translated = translate_text(description, translator)
        doc.body_md = "> 视频简介：" + translated.replace("\n", " ") + "\n\n" + doc.body_md
    doc.metadata.append(("输出语言", "简体中文（先按原语言转写，再翻译）"))
    if doc.transcript:
        models = list(dict.fromkeys(doc.transcript.translation_models + translator.used_models))
        doc.transcript.translation_models = models
        doc.metadata.append(("翻译模型", ", ".join(models)))


def retain_media(doc: Document, audio_path: str, work: Path,
                 output_dir: Path, settings: Settings) -> None:
    doc_dir = output_dir / doc.dirname
    if settings.keep_audio:
        doc_dir.mkdir(parents=True, exist_ok=True)
        filename = "audio" + Path(audio_path).suffix
        shutil.copy2(audio_path, doc_dir / filename)
        doc.attachments.append(filename)
    if settings.keep_chunks:
        for chunk in sorted((work / "chunks").glob("*.mp3")):
            target = doc_dir / "chunks" / chunk.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(chunk, target)
            doc.attachments.append(f"chunks/{chunk.name}")
