"""Application core: resolve identity -> extract -> write one document."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ingest2md.config import Settings
from ingest2md.extractors.base import Extractor
from ingest2md.identity import SourceIdentity, identity_from_document, resolve_identity
from ingest2md.model import Document, write_document
from ingest2md.router import find_extractor, normalize_reference
from ingest2md.runtime import RuntimeContext


@dataclass(frozen=True)
class IngestionRequest:
    source: str
    name: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedIngestion:
    raw_source: str
    reference: str
    source_name: str
    extractor: Extractor
    identity: SourceIdentity


@dataclass
class PreparedIngestion:
    request: IngestionRequest
    resolved: ResolvedIngestion
    document: Document
    canonical_key: str


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
    """Platform-agnostic execution of exactly one ingestion task.

    Batch mode may stop between resolve/extract/write to perform idempotency
    checks. Single mode composes the same three operations through ingest_one().
    """

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

    async def resolve_source(self, request: IngestionRequest | str) -> ResolvedIngestion:
        if isinstance(request, str):
            request = IngestionRequest(request)
        reference = normalize_reference(request.source)
        extractor = (
            find_extractor(reference, settings=self.settings, runtime=self.runtime)
            if self.runtime is not None
            else find_extractor(reference, settings=self.settings)
        )
        identity = await resolve_identity(extractor, reference)
        return ResolvedIngestion(
            raw_source=request.source,
            reference=reference,
            source_name=extractor.name,
            extractor=extractor,
            identity=identity,
        )

    async def extract_resolved(
        self,
        request: IngestionRequest,
        resolved: ResolvedIngestion,
    ) -> PreparedIngestion:
        document = await resolved.extractor.extract(resolved.reference, self.output_dir)
        document.ingestion_name = request.name.strip()
        document.ingestion_tags = tuple(
            tag.strip() for tag in request.tags if str(tag).strip()
        )

        final_identity = identity_from_document(document, resolved.reference)
        # Keep the stronger preflight semantic identity when extraction did not
        # expose source_type/source_id.
        if (
            final_identity.canonical_key.startswith(("ref:", "file:"))
            and not resolved.identity.canonical_key.startswith(("ref:", "file:"))
        ):
            final_identity = resolved.identity
        document.canonical_key = final_identity.canonical_key

        return PreparedIngestion(
            request=request,
            resolved=resolved,
            document=document,
            canonical_key=final_identity.canonical_key,
        )

    def write_prepared(self, prepared: PreparedIngestion) -> IngestionResult:
        document = prepared.document
        output_path = write_document(document, self.output_dir, self.settings.formats)

        if (
            self.runtime is not None
            and self.settings.media_cache_enabled
            and not self.settings.media_cache_keep_success
        ):
            self.runtime.media_cache.discard(prepared.canonical_key)

        return IngestionResult(
            raw_source=prepared.request.source,
            reference=prepared.resolved.reference,
            source_name=prepared.resolved.source_name,
            source_type=document.source_type,
            source_id=document.source_id,
            title=document.title,
            output_path=output_path,
            canonical_key=prepared.canonical_key,
            document=document,
        )

    async def ingest_one(self, request: IngestionRequest | str) -> IngestionResult:
        if isinstance(request, str):
            request = IngestionRequest(request)
        resolved = await self.resolve_source(request)
        prepared = await self.extract_resolved(request, resolved)
        return self.write_prepared(prepared)
