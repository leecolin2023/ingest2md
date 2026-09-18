"""Content-reference routing: normalize then dispatch to the first matching adapter."""
from __future__ import annotations

from ingest2md.extractors import get_extractors
from ingest2md.extractors.base import Extractor
from ingest2md.urlutils import (
    existing_local_path, extract_first_url, host_of, normalize_reference, normalize_url,
)

__all__ = [
    "UnsupportedURLError", "find_extractor", "explain_route", "format_route_explanation",
    "host_of", "normalize_reference", "normalize_url",
]


class UnsupportedURLError(Exception):
    def __init__(self, reference: str, supported: list[Extractor]):
        lines = [f"暂不支持该输入类型: {reference}", "", "当前支持的通道:"]
        lines.extend(f"  - {e.name}: {e.description}" for e in supported)
        super().__init__("\n".join(lines))
        self.reference = reference
        self.supported = supported


def find_extractor(reference: str, settings=None) -> Extractor:
    supported = get_extractors(settings)
    for extractor in supported:
        if extractor.match(reference):
            return extractor
    raise UnsupportedURLError(reference, supported)


def _input_kind(raw: str, normalized: str) -> str:
    if existing_local_path(raw):
        return "本地文件"
    stripped = (raw or "").strip().strip("\"'")
    if stripped.startswith(("http://", "https://")):
        return "URL"
    if extract_first_url(raw):
        return "App 分享文本 / 含 URL 文本"
    if stripped.upper().startswith("BV") and "bilibili.com/video/" in normalized:
        return "Bilibili BV 号"
    return "Content Reference"


def explain_route(raw: str) -> dict:
    """Resolve a content reference without fetching/downloading its content."""
    normalized = normalize_reference(raw)
    extractor = find_extractor(normalized)
    plan = list(getattr(extractor, "acquisition_plan", ()) or (extractor.description,))
    backend = getattr(extractor, "backend", "")
    return {
        "input_kind": _input_kind(raw, normalized),
        "normalized": normalized,
        "source": extractor.name,
        "adapter": type(extractor).__name__,
        "backend": backend,
        "plan": plan,
    }


def format_route_explanation(report: dict) -> str:
    lines = [
        "ingest2md 路由说明（dry-run）",
        f"输入类型: {report['input_kind']}",
        f"规范化输入: {report['normalized']}",
        f"识别来源: {report['source']}",
        f"Adapter: {report['adapter']}",
    ]
    if report.get("backend"):
        lines.append(f"Backend: {report['backend']}")
    lines.append("处理计划:")
    lines.extend(f"  {i}. {step}" for i, step in enumerate(report["plan"], 1))
    lines.extend(["", "仅解释路由；未抓取、未下载、未调用模型，也不会生成 Markdown。"])
    return "\n".join(lines)
