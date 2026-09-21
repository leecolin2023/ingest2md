"""Small persistent media cache for retry durability."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


class MediaCache:
    """Cache downloaded media between failed attempts.

    The cache is intentionally content-task scoped rather than a general HTTP
    cache. Successful ingestion may discard entries; failed ingestion leaves
    them available for the next retry/resume.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _digest(canonical_key: str) -> str:
        return hashlib.sha256(canonical_key.encode("utf-8")).hexdigest()[:32]

    def get(self, canonical_key: str) -> Path | None:
        prefix = self._digest(canonical_key)
        matches = sorted(path for path in self.root.glob(prefix + ".*") if path.is_file())
        return matches[0] if matches else None

    def store(self, canonical_key: str, source: str | Path) -> Path:
        source_path = Path(source)
        suffix = source_path.suffix.lower() or ".bin"
        target = self.root / f"{self._digest(canonical_key)}{suffix}"
        temp = target.with_suffix(target.suffix + ".tmp")
        shutil.copy2(source_path, temp)
        temp.replace(target)
        return target

    def discard(self, canonical_key: str) -> None:
        prefix = self._digest(canonical_key)
        for path in self.root.glob(prefix + ".*"):
            if path.is_file():
                path.unlink(missing_ok=True)
