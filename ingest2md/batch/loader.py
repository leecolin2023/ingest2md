"""Load TXT, CSV and JSONL batch manifests."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ingest2md.batch.models import BatchItem


def _tags(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    if not text:
        return ()
    separator = ";" if ";" in text else ","
    return tuple(part.strip() for part in text.split(separator) if part.strip())


def _manifest_source(value: str, base_dir: Path) -> str:
    source = str(value or "").strip()
    if not source:
        return ""
    if "://" in source or "http://" in source or "https://" in source:
        return source
    if source.upper().startswith("BV"):
        return source
    candidate = Path(source).expanduser()
    if not candidate.is_absolute():
        relative = (base_dir / candidate).resolve()
        if relative.exists():
            return str(relative)
    return source


def load_batch(path: str | Path) -> list[BatchItem]:
    manifest = Path(path).expanduser().resolve()
    if not manifest.is_file():
        raise FileNotFoundError(f"批量任务文件不存在: {manifest}")

    suffix = manifest.suffix.lower()
    if suffix == ".txt":
        items = _load_txt(manifest)
    elif suffix == ".jsonl":
        items = _load_jsonl(manifest)
    elif suffix == ".csv":
        items = _load_csv(manifest)
    else:
        raise ValueError("批量任务文件仅支持 .txt / .jsonl / .csv")

    if not items:
        raise ValueError("批量任务文件中没有可处理的 source")
    return items


def _load_txt(path: Path) -> list[BatchItem]:
    items = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        items.append(BatchItem(_manifest_source(value, path.parent), line_number=line_number))
    return items


def _load_jsonl(path: Path) -> list[BatchItem]:
    items = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSONL 第 {line_number} 行不是合法 JSON: {exc}") from exc
        if not isinstance(record, dict) or not str(record.get("source") or "").strip():
            raise ValueError(f"JSONL 第 {line_number} 行必须包含非空 source")
        items.append(BatchItem(
            source=_manifest_source(str(record["source"]), path.parent),
            name=str(record.get("name") or "").strip(),
            tags=_tags(record.get("tags")),
            line_number=line_number,
        ))
    return items


def _load_csv(path: Path) -> list[BatchItem]:
    items = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "source" not in reader.fieldnames:
            raise ValueError("CSV 必须包含 source 列")
        for line_number, record in enumerate(reader, 2):
            source = str(record.get("source") or "").strip()
            if not source:
                continue
            items.append(BatchItem(
                source=_manifest_source(source, path.parent),
                name=str(record.get("name") or "").strip(),
                tags=_tags(record.get("tags")),
                line_number=line_number,
            ))
    return items
