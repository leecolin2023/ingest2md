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

你必须采用“局部补丁”方式，不得返回整段改写后的文本：
1. 只返回 JSON 对象，格式为 {"edits":[{"id":0,"old":"原文中的精确片段","new":"替换后的片段"}]}。
2. id 必须是 target_segments 中的整数 id；只能修改 target_segments，不能修改 context_before/context_after。
3. old 必须是对应 target segment.text 中连续、逐字一致的子串，并且在该段中只出现一次。
4. old 不得等于整段原文；new 只能是替换 old 的局部结果，不得返回整段文本。
5. old 和 new 都不能为空；new 不得包含换行，且不要用过长文本替换短片段。不确定时不要提交该条修改。
6. 不要借校对之名删除内容或添加事实。不要修改时间戳。
7. 若无需修改，返回 {"edits":[]}。source_hints 只是高置信参考，不确定时保留原文。
"""

_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


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


def _validate_and_apply_edits(
    data: dict,
    expected_ids: list[int],
    source_texts: list[str],
) -> tuple[list[str], list[str]]:
    """Validate localized edits and apply only exact, non-overlapping source spans."""
    edits = data.get("edits")
    if not isinstance(edits, list):
        raise RuntimeError("LLM normalization 输出缺少 edits 数组")
    if len(expected_ids) != len(source_texts):
        raise RuntimeError("LLM normalization 内部 segment 映射长度不一致")

    source_by_id = dict(zip(expected_ids, source_texts))
    output = list(source_texts)
    warnings: list[str] = []
    candidates: list[dict[str, int | str]] = []

    def reject(number: int, segment_id: object, reason: str) -> None:
        warnings.append(
            f"edit #{number} (segment id={segment_id}) 已拒绝：{reason}"
        )

    for number, item in enumerate(edits, start=1):
        if not isinstance(item, dict):
            reject(number, "?", "修改项不是对象")
            continue

        segment_id = item.get("id")
        if type(segment_id) is not int:
            reject(number, segment_id, "id 必须是整数")
            continue
        if segment_id not in source_by_id:
            reject(number, segment_id, "id 不属于本次 target_segments")
            continue

        old = item.get("old")
        new = item.get("new")
        if not isinstance(old, str) or not old.strip():
            reject(number, segment_id, "old 必须是非空原文片段")
            continue
        if not isinstance(new, str) or not new.strip():
            reject(number, segment_id, "new 必须是非空替换文本")
            continue
        if "\n" in new or "\r" in new:
            reject(number, segment_id, "new 不得跨行或重写 segment 结构")
            continue
        if old == new:
            continue

        source = source_by_id[segment_id]
        if old == source:
            reject(number, segment_id, "不允许把整段文本作为替换范围")
            continue
        if len(new) >= len(source):
            reject(number, segment_id, "new 长度不小于整段原文，疑似整段改写")
            continue
        if len(new) > max(24, len(old) * 4):
            reject(number, segment_id, "new 过长，疑似非局部替换")
            continue
        occurrences = source.count(old)
        if occurrences != 1:
            reject(
                number,
                segment_id,
                f"old 在原文中出现 {occurrences} 次，无法唯一定位",
            )
            continue

        start = source.find(old)
        candidates.append({
            "number": number,
            "id": segment_id,
            "start": start,
            "end": start + len(old),
            "old": old,
            "new": new,
        })

    # If two proposed patches touch overlapping source spans, reject both rather
    # than letting model output order decide which edit wins.
    conflicting: set[int] = set()
    for left in range(len(candidates)):
        a = candidates[left]
        for right in range(left + 1, len(candidates)):
            b = candidates[right]
            if a["id"] != b["id"]:
                continue
            if max(a["start"], b["start"]) < min(a["end"], b["end"]):
                conflicting.update((left, right))

    for index in sorted(conflicting):
        candidate = candidates[index]
        reject(
            int(candidate["number"]),
            candidate["id"],
            "与同一 segment 的另一条修改范围重叠",
        )

    accepted = [
        candidate
        for index, candidate in enumerate(candidates)
        if index not in conflicting
    ]
    index_by_id = {segment_id: index for index, segment_id in enumerate(expected_ids)}
    for segment_id in expected_ids:
        text = source_by_id[segment_id]
        segment_edits = sorted(
            (edit for edit in accepted if edit["id"] == segment_id),
            key=lambda edit: int(edit["start"]),
            reverse=True,
        )
        for edit in segment_edits:
            start = int(edit["start"])
            end = int(edit["end"])
            # Positions were validated against the untouched source, and
            # right-to-left application keeps all remaining positions stable.
            text = text[:start] + str(edit["new"]) + text[end:]
        output[index_by_id[segment_id]] = text

    return output, warnings


def _normalize_window(
    segments: list[Segment],
    start: int,
    end: int,
    hints: NormalizationHints,
    settings: Settings,
    model: str,
    session_id: str,
) -> tuple[list[str], list[str]]:
    ids = list(range(start, end))
    source_texts = [segments[index].text for index in ids]
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
            "edits": [
                {
                    "id": ids[0],
                    "old": "<exact, unique substring from that segment>",
                    "new": "<replacement for that substring>",
                }
            ] if ids else []
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
    return _validate_and_apply_edits(parsed, ids, source_texts)


def normalize_segments_with_llm(
    segments: list[Segment],
    hints: NormalizationHints,
    settings: Settings,
) -> tuple[list[str], str, list[str]]:
    """Best-effort patch-based normalization with per-window basic fallback."""
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
            normalized, edit_warnings = _normalize_window(
                segments,
                start,
                end,
                hints,
                settings,
                model,
                session_id,
            )
            output[start:end] = normalized
            warnings.extend(
                f"segments {start + 1}-{end}: {warning}"
                for warning in edit_warnings
            )
        except Exception as exc:
            warnings.append(
                f"segments {start + 1}-{end} 保留 basic 结果: {exc}"
            )
    return output, model, warnings
