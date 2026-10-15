"""Repo-local paths for the developer tools in this directory.

Every tool here is run from a checkout, so derive locations from this file
instead of hard-coding an absolute path. The model/example caches are optional:
they only exist after the SenseVoice weights have been downloaded.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Keep `import ingest2md` working without an editable install.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Where the SenseVoice ONNX weights and the model's own example audio are
# expected. Both are gitignored local caches.
CACHE_DIR = REPO_ROOT / ".modelscope-cache"
MODEL_DIR = CACHE_DIR / "sherpa-sensevoice"
EXAMPLE_DIR = CACHE_DIR / "example"


def require(path: Path, what: str) -> Path:
    """Fail with an actionable message instead of a bare FileNotFoundError."""
    if not path.exists():
        raise SystemExit(
            f"{what} not found: {path}\n"
            "Download the SenseVoiceSmall ONNX export first "
            "(see the 'Validate the frontend' section of the docs), or point the "
            "tool at an existing directory."
        )
    return path
