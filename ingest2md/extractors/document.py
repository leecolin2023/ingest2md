"""PDF/Office documents delegated to Microsoft MarkItDown."""
from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import unquote, urlparse

from ingest2md.model import Document
from ingest2md.urlutils import host_of

DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}


def _suffix(reference: str) -> str:
    try:
        path = Path(reference).expanduser()
        if path.is_file():
            return path.suffix.lower()
    except (OSError, ValueError):
        pass
    try:
        return Path(unquote(urlparse(reference).path)).suffix.lower()
    except ValueError:
        return ""


class DocumentExtractor:
    name = "PDF / Office 文档"
    description = "PDF / DOCX / PPTX / XLSX → MarkItDown → Markdown"
    acquisition_plan = (
        "识别文档格式（PDF / DOCX / PPTX / XLSX）",
        "交给 Microsoft MarkItDown 转换",
        "包装为 ingest2md Document 并输出 Markdown",
    )

    def match(self, reference: str) -> bool:
        return _suffix(reference) in DOCUMENT_EXTENSIONS

    async def extract(self, reference: str, output_dir: Path) -> Document:
        return await asyncio.to_thread(self._extract, reference)

    def _extract(self, reference: str) -> Document:
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise ImportError(
                '文档转换是可选能力，请安装：python -m pip install "ingest2md[documents]"'
            ) from exc

        local_path: Path | None = None
        try:
            candidate = Path(reference).expanduser()
            if candidate.is_file():
                local_path = candidate.resolve()
        except (OSError, ValueError):
            pass
        source = str(local_path) if local_path else reference
        result = MarkItDown(enable_plugins=False).convert(source)
        body = (getattr(result, "markdown", "") or "").strip()
        if not body:
            raise RuntimeError("MarkItDown 未返回可读 Markdown")

        if local_path:
            title = getattr(result, "title", None) or local_path.stem
            source_url = local_path.as_uri()
            origin = "本地文档"
        else:
            parsed = urlparse(reference)
            stem = Path(unquote(parsed.path)).stem
            title = getattr(result, "title", None) or stem or host_of(reference) or "文档"
            source_url = reference
            origin = host_of(reference) or "远程文档"
        ext = _suffix(reference).lstrip(".").upper()
        return Document(
            title=title,
            source_url=source_url,
            source_type="document",
            metadata=[("来源", origin), ("文档格式", ext), ("转换后端", "Microsoft MarkItDown")],
            body_md=body,
        )
