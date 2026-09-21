"""Optional presentation-layer transcript correction.

Raw TranscriptResult segments remain untouched. This module only improves text
that is already being rendered for human/LLM reading.
"""
from __future__ import annotations

import logging
import re
import uuid

import requests

from ingest2md import __version__
from ingest2md.config import Settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是转写文本校对器。只做最小必要校正：
1. 修正明显 ASR 错字、专有名词、英文产品名、标点和断句；
2. 完整保留原意、信息、数字、语气和重复表达；
3. 不总结、不删减、不扩写、不解释、不改变事实；
4. 不新增原文没有的内容；
5. 只返回校正后的正文，不要加说明。"""


class TranscriptEnhancer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session_id = str(uuid.uuid4())

    @property
    def model(self) -> str:
        return (self.settings.transcript_enhance_model or self.settings.llm_model).strip()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key.strip()}",
            "User-Agent": f"ingest2md/{__version__}",
        }
        if "opencode.ai" in self.settings.llm_base_url.lower():
            headers["x-opencode-session"] = self.session_id
        return headers

    @staticmethod
    def _extract_text(value) -> str:
        if isinstance(value, list):
            value = "".join(
                item.get("text", "") for item in value if isinstance(item, dict)
            )
        return str(value or "").strip()

    def _post(self, path: str, payload: dict) -> dict:
        response = requests.post(
            self.settings.llm_base_url.rstrip("/") + path,
            headers=self._headers(),
            json=payload,
            timeout=180,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Transcript enhancer HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("Transcript enhancer 返回非 JSON 数据") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Transcript enhancer 返回非对象 JSON")
        return data

    def enhance_text(self, text: str) -> str:
        if not self.settings.llm_api_key.strip():
            raise ValueError("transcript_enhance=llm 但未配置 llm_api_key")
        if not self.model:
            raise ValueError("transcript_enhance=llm 但未配置模型")

        if self.settings.llm_api == "responses":
            data = self._post("/responses", {
                "model": self.model,
                "instructions": _SYSTEM_PROMPT,
                "input": text,
            })
            value = data.get("output_text")
            if value is None:
                value = "\n".join(
                    part.get("text", "")
                    for item in data.get("output", [])
                    for part in item.get("content", [])
                    if part.get("type") in {"output_text", "text"}
                )
            result = self._extract_text(value)
        else:
            data = self._post("/chat/completions", {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            })
            try:
                result = self._extract_text(data["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(
                    f"Transcript enhancer chat 响应结构异常: {str(data)[:300]}"
                ) from exc

        if not result:
            raise RuntimeError("Transcript enhancer 返回空文本")
        return result


def enhance_markdown(markdown: str, settings: Settings) -> str:
    """Enhance paragraph bodies while preserving timestamp/chapter headings."""

    if settings.transcript_enhance != "llm" or not markdown.strip():
        return markdown

    enhancer = TranscriptEnhancer(settings)
    parts = re.split(r"(?m)(?=^###\s)", markdown)
    rendered: list[str] = []
    try:
        for part in parts:
            if not part.strip():
                continue
            if part.startswith("### "):
                heading, sep, body = part.partition("\n")
                if not sep or not body.strip():
                    rendered.append(part.rstrip())
                    continue
                rendered.append(heading.rstrip() + "\n\n" + enhancer.enhance_text(body.strip()))
            else:
                rendered.append(enhancer.enhance_text(part.strip()))
        return "\n\n".join(rendered).strip()
    except Exception as exc:
        logger.warning("转写文字增强失败，回退原始转写: %s", exc)
        return markdown
