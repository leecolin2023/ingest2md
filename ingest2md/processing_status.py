"""Synchronize Skill processing status across the archive repositories.

Skill results are archived in HarnessLab/materials or knowledge-archive. This
module uses the explicit output/processing-status.json mapping, not the
presence of local derivative directories. The status means archived artifacts
exist, not that independent review execution or audio checks were verified.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from filelock import FileLock

from .source_index import (
    SOURCE_INDEX_FILENAME, SOURCE_INDEX_HEADER, SOURCE_INDEX_SEPARATOR,
    SOURCE_INDEX_TITLE, _escape_cell, _is_separator_row,
    _product_key, _render_row, _split_row, _write,
)


def _sources(output_dir: Path) -> list[str]:
    names = [p.name for p in output_dir.glob("*.md")
             if p.name != SOURCE_INDEX_FILENAME]
    names.extend(p.name + "/content.md" for p in output_dir.iterdir()
                 if p.is_dir() and (p / "content.md").is_file())
    return sorted(names)


def _entries(output_dir: Path) -> dict[str, dict]:
    path = output_dir / "processing-status.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("Manifest entries must be a list")
    result = {}
    for entry in entries:
        source = entry.get("source")
        if not isinstance(source, str) or not source or source in result:
            raise ValueError(f"Duplicate or invalid source: {source!r}")
        result[source] = entry
    return result


def _method(entry: dict) -> str:
    if entry.get("method") == "Refinement" and entry.get("refinement"):
        return "Refinement"
    if (entry.get("method") == "DeepRead + Learning"
            and entry.get("deep_read") and entry.get("learning")):
        return "DeepRead + Learning"
    return "未处理"


def build_inventory(output_dir: Path) -> list[dict[str, str]]:
    archive = _entries(Path(output_dir))
    inventory = []
    for source in _sources(Path(output_dir)):
        entry = archive.get(source, {})
        method = _method(entry)
        inventory.append({
            "source": source, "method": method,
            "read": "是" if method != "未处理" else "否",
            "refinement": entry.get("refinement", ""),
            "deep_read": entry.get("deep_read", ""),
            "learning": entry.get("learning", ""),
        })
    return inventory


def sync_processing_status(output_dir: Path) -> dict[str, int]:
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        raise FileNotFoundError(output_dir)
    inventory = build_inventory(output_dir)
    index = output_dir / SOURCE_INDEX_FILENAME
    with FileLock(str(index) + ".lock", timeout=30):
        lines = index.read_text(encoding="utf-8").splitlines() if index.is_file() else []
        if lines and lines[0].strip() != SOURCE_INDEX_TITLE:
            raise ValueError(f"Unrelated index: {index}")
        expected_headers = [
            ["链接", "Extractor", "产物路径", "日期"],
            ["链接", "Extractor", "产物路径", "日期", "是否已精读"],
        ]
        header = next((i for i, line in enumerate(lines)
                       if _split_row(line) in expected_headers), -1)
        existing = {}
        suffix = []
        if header >= 0:
            pos = header + 2
            while pos < len(lines) and lines[pos].strip().startswith("|"):
                if not _is_separator_row(lines[pos]):
                    fields = _split_row(lines[pos])
                    if len(fields) >= 4:
                        existing[_product_key(fields[2])] = fields
                pos += 1
            suffix = lines[pos:]
        rows = []
        for item in inventory:
            source = item["source"]
            old = existing.get(source)
            date_match = re.match(r"^(\d{4})(\d{2})(\d{2})__", source)
            date = ("-".join(date_match.groups()) if date_match else "—")
            link, extractor = (("本地视频", "LocalMediaExtractor")
                               if source.endswith("/content.md")
                               else ("—", "UnindexedSource"))
            if old:
                link, extractor, date = old[0], old[1], old[3]
            rows.append(_render_row(link, extractor, source, date, item["read"]))
        prefix = [
            SOURCE_INDEX_TITLE, "",
            "转写索引由 ingest2md 维护；是否已精读由 processing_status 按 JSON 归档映射同步。",
            "", SOURCE_INDEX_HEADER, SOURCE_INDEX_SEPARATOR,
        ]
        _write(index, prefix + rows + suffix)

    total = len(inventory)
    learning = sum(item["method"] == "DeepRead + Learning" for item in inventory)
    refinement = sum(item["method"] == "Refinement" for item in inventory)
    unread = sum(item["read"] == "否" for item in inventory)
    report = output_dir.parent / "PROCESSING_INDEX.md"
    result_lines = [
        "# Ingest2MD 素材处理索引", "",
        "以 output 中原稿及 output/processing-status.json 的归档映射为依据。",
        "",
        f"原稿 **{total}** 篇；DeepRead + Learning **{learning}** 篇；"
        f"Refinement **{refinement}** 篇；未精读 **{unread}** 篇。",
        "",
        "已精读表示相应 Skill 产物已归档，不代表经过独立事实核验、人工核听或执行隔离验收。",
        "",
        "新产物入库后先更新 JSON，运行 python -m ingest2md.processing_status --output-dir output。",
        "",
        "| 原稿 | 加工方式 | 是否已精读 | 归档产物 |",
        "|---|---|---|---|",
    ]
    for item in inventory:
        if item["method"] == "Refinement":
            artifacts = f'[Refinement]({item["refinement"]})'
        elif item["method"] == "DeepRead + Learning":
            artifacts = f'[DeepRead]({item["deep_read"]}) · [Learning]({item["learning"]})'
        else:
            artifacts = "—"
        result_lines.append(f'| output/{_escape_cell(item["source"])} | '
                            f'{item["method"]} | {item["read"]} | {artifacts} |')
    report.write_text("\n".join(result_lines) + "\n", encoding="utf-8")
    return dict(total=total, learning=learning, refinement=refinement, unread=unread)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()
    print(sync_processing_status(args.output_dir))


if __name__ == "__main__":
    main()
