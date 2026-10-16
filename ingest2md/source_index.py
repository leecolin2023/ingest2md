"""Maintain ``<output_dir>/sources.md``: 链接 -> Extractor -> 产物路径 索引。

每次成功写出产物后追加或刷新一行表格，让生成结果可以回溯到来源链接。
索引失败绝不能影响转写本身，调用方需要自行捕获异常。
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

SOURCE_INDEX_FILENAME = "sources.md"
SOURCE_INDEX_TITLE = "# 转写链接记录"
SOURCE_INDEX_COLUMNS = ("链接", "Extractor", "产物路径", "日期")
SOURCE_INDEX_HEADER = "| " + " | ".join(SOURCE_INDEX_COLUMNS) + " |"
SOURCE_INDEX_SEPARATOR = "|" + "---|" * len(SOURCE_INDEX_COLUMNS)


def _escape_cell(value: str) -> str:
    return str(value or "").replace("|", "\\|").strip() or "—"


def _split_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", inner)]


def _is_separator_row(line: str) -> bool:
    if not line.strip().startswith("|"):
        return False
    cells = [cell for cell in _split_row(line) if cell]
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells)


def _normalized_link(value: str) -> str:
    return value.strip().strip("`").rstrip("/").lower()


def _product_display(product: Path, output_dir: Path) -> str:
    try:
        return product.relative_to(output_dir).as_posix()
    except ValueError:
        return product.as_posix()


def _product_name(cell_or_display: str) -> str:
    value = cell_or_display.strip().strip("`").strip()
    return Path(value.replace("\\|", "|")).name


def _render_row(link: str, extractor: str, product_display: str, date: str) -> str:
    return (
        f"| {_escape_cell(link)} | {_escape_cell(extractor)} "
        f"| `{_escape_cell(product_display)}` | {_escape_cell(date)} |"
    )


def _write(index_path: Path, lines: list[str]) -> None:
    index_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def record_source(
    output_dir: Path,
    link: str,
    extractor: str,
    product: Path,
    date: str | None = None,
) -> Path:
    """Append or refresh the product row for ``link`` in ``sources.md``.

    Deduplication matches either the same link or the same product file name,
    so re-running one reference updates its row instead of duplicating it.
    Hand-written sections below the table are preserved untouched.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / SOURCE_INDEX_FILENAME
    date_text = date or datetime.now().strftime("%Y-%m-%d")
    display = _product_display(Path(product), output_dir)
    new_row = _render_row(link, extractor, display, date_text)

    if not index_path.is_file():
        _write(index_path, [SOURCE_INDEX_TITLE, "", SOURCE_INDEX_HEADER, SOURCE_INDEX_SEPARATOR, new_row])
        return index_path

    lines = index_path.read_text(encoding="utf-8").splitlines()
    header_at = next(
        (
            i
            for i, line in enumerate(lines)
            if line.strip().startswith("|") and _split_row(line) == list(SOURCE_INDEX_COLUMNS)
        ),
        None,
    )
    if header_at is None:
        lines.extend(["", SOURCE_INDEX_HEADER, SOURCE_INDEX_SEPARATOR, new_row])
        _write(index_path, lines)
        return index_path

    separator_at = header_at + 1
    if separator_at >= len(lines) or not _is_separator_row(lines[separator_at]):
        lines.insert(separator_at, SOURCE_INDEX_SEPARATOR)
    first_data_at = header_at + 2

    new_link = _normalized_link(link)
    new_name = _product_name(display)
    matched_at = None
    cursor = first_data_at
    while cursor < len(lines) and lines[cursor].strip().startswith("|"):
        if _is_separator_row(lines[cursor]):
            cursor += 1
            continue
        cells = _split_row(lines[cursor])
        if len(cells) >= len(SOURCE_INDEX_COLUMNS):
            same_link = bool(new_link) and _normalized_link(cells[0]) == new_link
            same_product = bool(new_name) and _product_name(cells[2]) == new_name
            if same_link or same_product:
                matched_at = cursor
                break
        cursor += 1

    if matched_at is not None:
        lines[matched_at] = new_row
    else:
        lines.insert(cursor, new_row)
    _write(index_path, lines)
    return index_path
