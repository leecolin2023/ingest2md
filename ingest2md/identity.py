"""Stable content identity used for idempotent ingestion."""
from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceIdentity:
    """Identity known before or after acquisition.

    Platform adapters may provide a semantic identity (for example
    youtube:VIDEO_ID). Unknown sources fall back to a stable reference/file key.
    """

    canonical_key: str
    source_type: str = ""
    source_id: str = ""


def identity_from_parts(source_type: str, source_id: str, reference: str) -> SourceIdentity:
    source_type = str(source_type or "").strip()
    source_id = str(source_id or "").strip()
    if source_type and source_id:
        return SourceIdentity(f"{source_type}:{source_id}", source_type, source_id)
    return fallback_identity(reference)


def fallback_identity(reference: str) -> SourceIdentity:
    """Build a stable identity without network access.

    Existing local files include size and mtime so replacing a file at the same
    path is treated as new content. URLs/references use their normalized value.
    """

    value = str(reference or "").strip()
    try:
        path = Path(value).expanduser()
        if path.is_file():
            stat = path.stat()
            material = f"file:{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
            digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
            return SourceIdentity(f"file:{digest}")
    except (OSError, ValueError):
        pass

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return SourceIdentity(f"ref:{digest}")


async def resolve_identity(extractor, reference: str) -> SourceIdentity:
    """Ask an adapter for semantic identity, with a safe generic fallback."""

    resolver = getattr(extractor, "identity", None)
    if resolver is not None:
        value = resolver(reference)
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, SourceIdentity) and value.canonical_key:
            return value
    return fallback_identity(reference)


def identity_from_document(document, reference: str) -> SourceIdentity:
    return identity_from_parts(
        getattr(document, "source_type", ""),
        getattr(document, "source_id", ""),
        reference,
    )
