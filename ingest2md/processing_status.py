"""Synchronize Skill completion for every raw output and regenerate both indexes.

Usage: python -m ingest2md.processing_status --output-dir output

Read rule: either one existing Transcript Refinement artifact, or a complete
DeepRead + Learning pair. Presence is an artifact check, not a verified
independent Review/DeepRead execution trace or audio quality check.
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from filelock import FileLock

from .source_index import (
    SOURCE_INDEX_FILENAME, SOURCE_INDEX_HEADER, SOURCE_INDEX_SEPARATOR,
    SOURCE_INDEX_TITLE, _escape_cell, _is_separator_row,
    _product_key, _render_row, _split_row, _write,
)


def _source_files(output_dir: Path) -> list[Path]:
    items = [p for p in output_dir.iterdir()
             if p.is_file() and p.suffix.lower() == ".md"
             and p.name != SOURCE_INDEX_FILENAME]
    items += [p / "content.md" for p in output_dir.iterdir()
              if p.is_dir() and (p / "content.md").is_file()]
    return sorted(items, key=lambda x: x.relative_to(output_dir).as_posix())


def _legacy_links(ref_dir: Path) -> dict[str, str]:
    readme = ref_dir / "README.md"
    if not readme.is_file():
        return {}
    links = {}
    for line in readme.read_text(encoding="utf-8").splitlines():
        original = re.search(r"\[原稿\]\(\.\./output/(.+?\.md)\)", line)
        target = re.search(r"\|\s*\[[^\]]+\]\(\./(.+?\.md)\)", line)
        if original and target:
            links[unquote(original.group(1))] = unquote(target.group(1))
    return links


def _source_metadata(path: Path, output_dir: Path) -> tuple[str, str, str]:
    display = path.relative_to(output_dir).as_posix()
    m = re.match(r"^(\d{4})(\d{2})(\d{2})__", path.parent.name
                 if path.name == "content.md" else path.name)
    date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else "—"
    if path.name == "content.md":
        return "—", "LocalVideo", date
    # Header metadata is read only for the few sources missing from the index.
    head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:20])
    original = re.search(r"^>\s*原文链接:\s*(\S+)", head, re.MULTILINE)
    link = original.group(1) if original else "—"
    if link.startswith("file://"):
        link = "—"
    extractor = ("BilibiliExtractor" if "bilibili.com" in link
                 else "DouyinExtractor" if "douyin.com" in link
                 else "UnindexedSource")
    return link, extractor, date


def build_inventory(output_dir: Path) -> list[dict[str, str]]:
    output_dir = Path(output_dir)
    parent = output_dir.parent
    ref_dir, learn_dir = parent / "output-Refinement", parent / "output-Learning"
    refined = {p.name for p in ref_dir.glob("*.md")}
    learning = {p.name for p in learn_dir.glob("*.md")}
    legacy = _legacy_links(ref_dir)
    inventory = []
    for src in _source_files(output_dir):
        display = src.relative_to(output_dir).as_posix()
        stem = src.parent.name if src.name == "content.md" else src.stem
        mapped_ref = legacy.get(display, stem + ".md")
        has_ref = mapped_ref in refined
        has_d = stem + "__DeepRead.md" in learning
        has_l = stem + "__Learning.md" in learning
        if has_d and has_l:
            kind = "DeepRead + Learning"
        elif has_ref:
            kind = "Refinement"
        elif has_d or has_l:
            kind = "部分产物（待补全）"
        else:
            kind = "未处理"
        link, extractor, date = _source_metadata(src, output_dir)
        inventory.append(dict(display=display, kind=kind,
                              read="是" if kind in {"Refinement", "DeepRead + Learning"} else "否",
                              link=link, extractor=extractor, date=date))
    return inventory


def sync_processing_status(output_dir: Path) -> dict[str, int]:
    """Lock, reconcile existing metadata, append missing sources, and publish."""
    output_dir = Path(output_dir)
    inventory = build_inventory(output_dir)
    index = output_dir / SOURCE_INDEX_FILENAME
    index.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(index) + ".lock", timeout=30):
        lines = index.read_text(encoding="utf-8").splitlines() if index.is_file() else []
        if lines and lines[0].strip() != SOURCE_INDEX_TITLE:
            raise ValueError(f"Refusing to overwrite unrelated file: {index}")
        header_pos = next((i for i, line in enumerate(lines)
                           if line.strip().startswith("|")
                           and _split_row(line) in (
                               list(("链接", "Extractor", "产物路径", "日期")),
                               list(("链接", "Extractor", "产物路径", "日期", "是否已精读")),
                           )), -1)
        existing = {}
        preface = lines[:header_pos] if header_pos >= 0 else [
            SOURCE_INDEX_TITLE, "", "本文件由 ingest2md 自动维护；精读状态以已提交的 Skill 产物为准。",
            ""
        ]
        suffix = []
        if header_pos >= 0:
            cursor = header_pos + 2
            while cursor < len(lines) and lines[cursor].strip().startswith("|"):
                if not _is_separator_row(lines[cursor]):
                    row = _split_row(lines[cursor])
                    if len(row) >= 4:
                        existing[_product_key(row[2])] = row
                cursor += 1
            suffix = lines[cursor:]
        rows = []
        for item in inventory:
            old = existing.get(item["display"])
            if old:
                link, extractor, date = old[0], old[1], old[3]
            else:
                link, extractor, date = item["link"], item["extractor"], item["date"]
            rows.append(_render_row(link, extractor, item["display"],
                                    date, item["read"]))
        _write(index, preface + [SOURCE_INDEX_HEADER, SOURCE_INDEX_SEPARATOR]
               + rows + suffix)

    total = len(inventory)
    complete_learning = sum(i["kind"] == "DeepRead + Learning" for i in inventory)
    refined_count = sum(i["kind"] == "Refinement" for i in inventory)
    partial = sum(i["kind"] == "部分产物（待补全）" for i in inventory)
    unread = sum(i["read"] == "否" for i in inventory)
    report = parent_index = output_dir.parent / "output-Learning" / "PROCESSING_INDEX.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report_lines = [
        "# Ingest2MD 全量处理索引（自动对账）",
        "",
        "本表以 `output/` 中实际可读原稿为基准，通过文件名与旧版 Refinement README 的映射，",
        "检查 `output-Refinement/` 及 `output-Learning/` 实际产物。",
        "",
        f"- 原稿总数：**{total}**",
        f"- DeepRead + Learning 双稿：**{complete_learning}**",
        f"- Refinement 单稿：**{refined_count}**",
        f"- 不完整双稿：**{partial}**",
        f"- 未精读：**{unread}**",
        "",
        "> **状态规则**：存在 Refinement 单稿，或同时存在 DeepRead 与 Learning 两份文件，则“是否已精读=是”。",
        "> “已精读”仅证明相应文件已生成，不证明音频人工核对、事实独立核验或 SenseWright D/R 运行时隔离。",
        "> 重新运行本模块可按当前文件状态覆盖标记（若文件丢失则降回“否”）。",
        "",
        "## 原稿逐篇核对",
        "",
        "| 原稿 | 处理方式 | 是否已精读 |",
        "| --- | --- | --- |",
    ]
    for item in inventory:
        report_lines.append(
            f'| `output/{_escape_cell(item["display"])}` | '
            f'{item["kind"]} | {item["read"]} |'
        )
    report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return dict(total=total, learning=complete_learning, refinement=refined_count,
                partial=partial, unread=unread)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    opts = parser.parse_args()
    print(sync_processing_status(opts.output_dir))


if __name__ == "__main__":
    main()
