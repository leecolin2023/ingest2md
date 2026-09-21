"""TXT / JSONL / CSV batch source loaders."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ingest2md.engine import IngestionRequest


def _tags(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    if not text:
        return ()
    return tuple(part.strip() for part in text.split(",") if part.strip())


def load_batch_file(path: str | Path) -> list[IngestionRequest]:
    file = Path(path).expanduser().resolve()
    if not file.is_file():
        raise FileNotFoundError(f"批量输入文件不存在: {file}")

    suffix = file.suffix.lower()
    items: list[IngestionRequest] = []
    if suffix in {"", ".txt"}:
        for raw in file.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            items.append(IngestionRequest(source=line))
    elif suffix == ".jsonl":
        for number, raw in enumerate(file.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL 第 {number} 行不是合法 JSON: {exc}") from exc
            if not isinstance(payload, dict) or not str(payload.get("source") or "").strip():
                raise ValueError(f"JSONL 第 {number} 行必须包含非空 source")
            items.append(IngestionRequest(
                source=str(payload["source"]).strip(),
                name=str(payload.get("name") or "").strip(),
                tags=_tags(payload.get("tags")),
            ))
    elif suffix == ".csv":
        with file.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or "source" not in reader.fieldnames:
                raise ValueError("CSV 必须包含 source 列")
            for number, row in enumerate(reader, 2):
                source = str(row.get("source") or "").strip()
                if not source:
                    continue
                items.append(IngestionRequest(
                    source=source,
                    name=str(row.get("name") or "").strip(),
                    tags=_tags(row.get("tags")),
                ))
    else:
        raise ValueError("批量输入仅支持 TXT、JSONL、CSV")

    if not items:
        raise ValueError("批量输入中没有可处理任务")
    return items
