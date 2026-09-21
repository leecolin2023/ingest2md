"""Batch task models."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StoredTask:
    id: int
    raw_source: str
    normalized_source: str
    name: str
    tags: tuple[str, ...]
    status: str
    attempts: int
