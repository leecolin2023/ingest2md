"""Maintain ``<output_dir>/sources.md`` without losing concurrent updates."""
from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from filelock import FileLock

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
    """Only scheme and host are case-insensitive; paths and queries are not."""
    raw = value.strip().strip("`")
    try:
        parts = urlsplit(raw)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return raw.rstrip("/")
        authority = parts.netloc
        prefix, at, hostport = authority.rpartition("@")
        if not at:
            hostport = authority
        if hostport.startswith("["):
            closing = hostport.find("]")
            hostport = hostport[:closing + 1].lower() + hostport[closing + 1:]
        else:
            host, separator, port = hostport.partition(":")
            hostport = host.lower() + (separator + port if separator else "")
        netloc = (prefix + "@" if at else "") + hostport
        return urlunsplit((
            parts.scheme.lower(), netloc, parts.path.rstrip("/"), parts.query, parts.fragment,
        ))
    except ValueError:
        return raw.rstrip("/")


def _product_display(product: Path, output_dir: Path) -> str:
    try:
        return product.relative_to(output_dir).as_posix()
    except ValueError:
        return product.as_posix()


def _product_key(cell_or_display: str) -> str:
    """Compare the full relative product path, not just a shared basename."""
    return cell_or_display.strip().strip("`").replace("\\|", "|").strip()


def _render_row(link: str, extractor: str, product_display: str, date: str) -> str:
    return (
        f"| {_escape_cell(link)} | {_escape_cell(extractor)} "
        f"| `{_escape_cell(product_display)}` | {_escape_cell(date)} |"
    )


def _write(index_path: Path, lines: list[str]) -> None:
    """Publish a complete file atomically, preserving the prior index on failure."""
    contents = "\n".join(lines).rstrip("\n") + "\n"
    fd, temporary_name = tempfile.mkstemp(
        dir=index_path.parent, prefix=f".{index_path.name}.", suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, index_path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _record_source_locked(
    index_path: Path, link: str, extractor: str, display: str, date_text: str,
    obsolete_displays: frozenset[str] = frozenset(),
) -> None:
    new_row = _render_row(link, extractor, display, date_text)
    if not index_path.is_file():
        _write(index_path, [SOURCE_INDEX_TITLE, "", SOURCE_INDEX_HEADER, SOURCE_INDEX_SEPARATOR, new_row])
        return

    lines = index_path.read_text(encoding="utf-8").splitlines()
    # Do not append index data into an unrelated file also named sources.md.
    if not lines or lines[0].strip() != SOURCE_INDEX_TITLE:
        raise ValueError(f"Refusing to overwrite non-index document: {index_path}")
    header_at = next(
        (
            i for i, line in enumerate(lines)
            if line.strip().startswith("|") and _split_row(line) == list(SOURCE_INDEX_COLUMNS)
        ),
        None,
    )
    if header_at is None:
        lines.extend(["", SOURCE_INDEX_HEADER, SOURCE_INDEX_SEPARATOR, new_row])
        _write(index_path, lines)
        return

    separator_at = header_at + 1
    if separator_at >= len(lines) or not _is_separator_row(lines[separator_at]):
        lines.insert(separator_at, SOURCE_INDEX_SEPARATOR)
    first_data_at = header_at + 2

    new_link = _normalized_link(link)
    new_product = _product_key(display)
    matched = []
    cursor = first_data_at
    while cursor < len(lines) and lines[cursor].strip().startswith("|"):
        if not _is_separator_row(lines[cursor]):
            cells = _split_row(lines[cursor])
            if len(cells) >= len(SOURCE_INDEX_COLUMNS):
                same_link = bool(new_link) and _normalized_link(cells[0]) == new_link
                same_product = bool(new_product) and _product_key(cells[2]) == new_product
                # A title overwrite may remove a prior dated product,
                # even when this ingestion arrived through a different URL.
                obsolete_product = _product_key(cells[2]) in obsolete_displays
                if same_link or same_product or obsolete_product:
                    matched.append(cursor)
        cursor += 1

    if matched:
        lines[matched[0]] = new_row
        for index in reversed(matched[1:]):
            del lines[index]
    else:
        lines.insert(cursor, new_row)
    _write(index_path, lines)


def record_source(
    output_dir: Path,
    link: str,
    extractor: str,
    product: Path,
    date: str | None = None,
    obsolete_products: tuple[Path, ...] = (),
) -> Path:
    """Append or refresh the index under a stable cross-process file lock.

    The lock covers the full read/modify/write cycle, and os.replace makes
    published versions atomic. The caller handles indexing errors separately
    from a successful transcript output.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / SOURCE_INDEX_FILENAME
    display = _product_display(Path(product), output_dir)
    date_text = date or datetime.now().strftime("%Y-%m-%d")
    obsolete_displays = frozenset(
        _product_key(_product_display(Path(old), output_dir)) for old in obsolete_products
    )
    with FileLock(str(index_path) + ".lock", timeout=30):
        _record_source_locked(
            index_path, link, extractor, display, date_text, obsolete_displays,
        )
    return index_path
