"""Optional OpenAI-compatible LLM transcript normalizer."""
from __future__ import annotations

import json
import re
import uuid

import requests

from ingest2md import __version__
from ingest2md.config import Settings
from ingest2md.transcription.model import Segment
from ingest2md.transcription.normalization import NormalizationHints

_SYSTEM_PROMPT = """你是逐字稿校对器，不是编辑、总结器或改写器。

任务：只修复 ASR 造成的明显文本问题，使逐字稿更可读、更稳定。
允许：恢复标点、修复明显的专有名词/英文拼写、合并被错误拆开的英文缩写、修复明显的 ASR 同音误识别。
禁止：总结、删减观点、补充事实、改变语气、翻译、重写论证、猜测音频中不存在的内容。

必须遵守：
1. 只返回 JSON，不要输出 Markdown 或解释。
2. 输出 segments 数量、id 与输入 target_segments 完全一致。
3. 不得修改时间戳；时间戳不在你的输出字段中。
4. 上下文段只用于理解，不能出现在输出中。
5. source_hints 只是高置信参考，不确定时保留原文。
"""

_CODE_FENCE_RE = re.compile(r"^\s*\`\`\`(?:json)?\s*|\s*\`\`\`\s*$", re.I)


def _headers(settings: Settings, session_id: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key.strip()}",
        "Content-Type": "application/json",
        "User-Agent": f"ingest2md/{__version__}",
    }
    if "opencode.ai" in settings.llm_base_url.lower():
        headers["x-opencode-session"] = session_id
    return headers


def _post(settings: Settings, path: str, payload: dict, session_id: str) -> dict:
    response = requests.post(
        settings.llm_base_url.rstrip("/") + path,
        json=payload,
        headers=_headers(settings, session_id),
        timeout=180,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"LLM normalization HTTP {response.status_code}: {response.text[:400]}"
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("LLM normalization 返回非 JSON 响应") from exc
    if not isinstance(data, dict):
        raise RuntimeError("LLM normalization 返回非对象 JSON")
    return data


def _extract_response_text(data: dict, api: str) -> str:
    if api == "responses":
        text = data.get("output_text")
        if text is None:
            text = "\n".join(
                content.get("text", "")
                for item in data.get("output", [])
                for content in item.get("content", [])
                if content.get("type") in {"output_text", "text"}
            )
        return str(text or "").strip()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"LLM normalization chat 响应结构异常: {str(data)[:300]}"
        ) from exc
    if isinstance(content, list):
        content = "".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict)
        )
    return str(content or "").strip()


def _parse_json(text: str) -> dict:
    text = _CODE_FENCE_RE.sub("", str(text or "").strip())
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("LLM normalization 未返回 JSON 对象")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM normalization JSON 解析失败") from exc
    if not isinstance(data, dict):
        raise RuntimeError("LLM normalization JSON 顶层必须是对象")
    return data


def _validate_window(
    data: dict,
    expected_ids: list[int],
    source_texts: list[str],
) -> list[str]:
    items = data.get("segments")
    if not isinstance(items, list) or len(items) != len(expected_ids):
        raise RuntimeError("LLM normalization segment 数量异常")

    by_id: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("LLM normalization segment 结构异常")
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("LLM normalization segment id 非法") from exc
        normalized = item.get("text")
        if not isinstance(normalized, str) or not normalized.strip():
            raise RuntimeError("LLM normalization 返回空文本")
        by_id[item_id] = normalized.strip()

    if set(by_id) != set(expected_ids):
        raise RuntimeError("LLM normalization 修改了 segment id")

    output = [by_id[item_id] for item_id in expected_ids]
    before = sum(len(value.strip()) for value in source_texts)
    after = sum(len(value.strip()) for value in output)
    if before > 0:
        ratio = after / before
        if ratio < 0.45 or ratio > 2.0:
            raise RuntimeError(
                f"LLM normalization 文本长度变化异常: {ratio:.2f}x"
            )
    return output


def _normalize_window(
    segments: list[Segment],
    start: int,
    end: int,
    hints: NormalizationHints,
    settings: Settings,
    model: str,
    session_id: str,
) -> list[str]:
    ids = list(range(start, end))
    request = {
        "source_hints": {
            "source_type": hints.source_type,
            "title": hints.title,
            "people": list(hints.people),
            "terms": list(hints.terms),
            "context": hints.compact_context(),
        },
        "context_before": segments[start - 1].text if start > 0 else "",
        "target_segments": [
            {"id": index, "text": segments[index].text}
            for index in ids
        ],
        "context_after": segments[end].text if end < len(segments) else "",
        "required_output": {
            "segments": [
                {"id": index, "text": "<normalized text>"}
                for index in ids
            ]
        },
    }
    user_text = json.dumps(request, ensure_ascii=False)

    if settings.llm_api == "responses":
        data = _post(
            settings,
            "/responses",
            {
                "model": model,
                "input": [{
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": _SYSTEM_PROMPT + "\n\n输入 JSON：\n" + user_text,
                    }],
                }],
            },
            session_id,
        )
    else:
        data = _post(
            settings,
            "/chat/completions",
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ],
            },
            session_id,
        )

    parsed = _parse_json(_extract_response_text(data, settings.llm_api))
    return _validate_window(
        parsed,
        ids,
        [segments[index].text for index in ids],
    )


def normalize_segments_with_llm(
    segments: list[Segment],
    hints: NormalizationHints,
    settings: Settings,
) -> tuple[list[str], str, list[str]]:
    """Best-effort smart normalization with per-window fallback."""
    if not settings.llm_api_key.strip():
        raise ValueError("transcript_normalization=llm 但未配置 llm_api_key")

    model = (settings.normalization_model or settings.llm_model).strip()
    if not model:
        raise ValueError("未配置 normalization_model 或 llm_model")

    window = max(1, settings.normalization_window_segments)
    output = [segment.text for segment in segments]
    warnings: list[str] = []
    session_id = str(uuid.uuid4())

    for start in range(0, len(segments), window):
        end = min(len(segments), start + window)
        try:
            normalized = _normalize_window(
                segments,
                start,
                end,
                hints,
                settings,
                model,
                session_id,
            )
            output[start:end] = normalized
        except Exception as exc:
            warnings.append(
                f"segments {start + 1}-{end} 保留 basic 结果: {exc}"
            )
    return output, model, warnings
