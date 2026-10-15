"""Application core: one content reference -> one written document."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ingest2md.config import Settings
from ingest2md.model import Document, write_document
from ingest2md.router import find_extractor, normalize_reference
from ingest2md.runtime import RuntimeContext


@dataclass(frozen=True)
class IngestionRequest:
    source: str
    name: str = ""
    tags: tuple[str, ...] = ()


@dataclass
class IngestionResult:
    raw_source: str
    reference: str
    source_name: str
    source_type: str
    source_id: str
    title: str
    output_path: Path
    canonical_key: str
    document: Document


class IngestionEngine:
    """Platform-agnostic execution of exactly one ingestion task."""

    def __init__(
        self,
        settings: Settings,
        output_dir: Path | None = None,
        runtime: RuntimeContext | None = None,
    ):
        self.settings = settings
        self.runtime = runtime
        self.output_dir = (
            runtime.output_dir
            if runtime is not None
            else (
                Path(output_dir).expanduser().resolve()
                if output_dir is not None
                else Path(settings.output_dir).expanduser().resolve()
            )
        )

    async def ingest_one(self, request: IngestionRequest | str) -> IngestionResult:
        if isinstance(request, str):
            request = IngestionRequest(request)

        reference = normalize_reference(request.source)
        extractor = (
            find_extractor(reference, settings=self.settings, runtime=self.runtime)
            if self.runtime is not None
            else find_extractor(reference, settings=self.settings)
        )
        document = await extractor.extract(reference, self.output_dir)
        output_path = write_document(document, self.output_dir, self.settings.formats)

        canonical_key = (
            f"{document.source_type}:{document.source_id}"
            if document.source_type and document.source_id
            else reference
        )
        return IngestionResult(
            raw_source=request.source,
            reference=reference,
            source_name=extractor.name,
            source_type=document.source_type,
            source_id=document.source_id,
            title=document.title,
            output_path=output_path,
            canonical_key=canonical_key,
            document=document,
        )
