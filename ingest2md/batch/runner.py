"""Serial, resumable batch runner with identity-aware retry semantics."""
from __future__ import annotations

import asyncio
import json
import logging

from ingest2md.batch.models import BatchItem, BatchSummary, config_fingerprint
from ingest2md.batch.store import TaskStore
from ingest2md.engine import IngestionEngine, IngestionRequest
from ingest2md.extractors.base import SourceUnavailableError
from ingest2md.router import UnsupportedURLError

logger = logging.getLogger(__name__)


def classify_error(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, (SourceUnavailableError, UnsupportedURLError)):
        return "unsupported", False
    if isinstance(exc, FileNotFoundError):
        return "input_missing", False
    if isinstance(exc, TimeoutError):
        return "timeout", True
    message = str(exc).lower()
    if any(token in message for token in ("timeout", "timed out", "read timeout")):
        return "timeout", True
    if any(token in message for token in (
        "connection reset", "connection aborted", "remote disconnected",
        "connection closed", "server disconnected",
    )):
        return "transient_network", True
    if "429" in message or "too many requests" in message:
        return "rate_limited", True
    if any(token in message for token in ("502", "503", "504", "temporarily unavailable")):
        return "transient_network", True
    if any(token in message for token in ("cookie", "登录", "login", "auth")):
        return "auth_required", False
    if any(token in message for token in ("无音轨", "invalid media", "媒体候选")):
        return "invalid_media", False
    if "asr" in message or "转写" in message:
        return "transcription_failed", False
    return "failed", False


class BatchRunner:
    def __init__(self, engine: IngestionEngine, store: TaskStore):
        self.engine = engine
        self.store = store

    @staticmethod
    def _request(task) -> IngestionRequest:
        return IngestionRequest(
            source=task["raw_source"],
            name=task["name"],
            tags=tuple(json.loads(task["tags_json"] or "[]")),
        )

    async def _run_one(
        self,
        task,
        fingerprint: str,
    ) -> None:
        task_id = int(task["id"])
        request = self._request(task)

        # New engine lifecycle: identity can be checked before expensive extract,
        # and final semantic identity is checked again before writing.
        if all(
            hasattr(self.engine, name)
            for name in ("resolve_source", "extract_resolved", "write_prepared")
        ):
            resolved = await self.engine.resolve_source(request)
            self.store.set_identity(
                task_id,
                resolved.identity.canonical_key,
                resolved.identity.source_type,
                resolved.identity.source_id,
            )
            duplicate = self.store.find_completed_by_canonical(
                resolved.identity.canonical_key,
                fingerprint,
                exclude_task_id=task_id,
            )
            if duplicate is not None:
                self.store.mark_duplicate(task_id, duplicate)
                logger.info("跳过重复内容: %s", resolved.identity.canonical_key)
                return

            prepared = await self.engine.extract_resolved(request, resolved)
            self.store.set_identity(
                task_id,
                prepared.canonical_key,
                prepared.document.source_type,
                prepared.document.source_id,
            )
            duplicate = self.store.find_completed_by_canonical(
                prepared.canonical_key,
                fingerprint,
                exclude_task_id=task_id,
            )
            if duplicate is not None:
                self.store.mark_duplicate(task_id, duplicate)
                logger.info("提取后识别为重复内容，跳过写入: %s", prepared.canonical_key)
                return

            result = self.engine.write_prepared(prepared)
        else:
            # Compatibility for lightweight custom/fake engines implementing the
            # v0.9 single-call contract.
            result = await self.engine.ingest_one(request)

        self.store.mark_success(task_id, result)
        logger.info("已保存: %s", result.output_path)

    async def run(
        self,
        items: list[BatchItem],
        *,
        resume: bool = False,
        take: int = 0,
        retry_failed: bool = False,
    ) -> BatchSummary:
        fingerprint = config_fingerprint(self.engine.settings)
        task_ids = self.store.register(items, fingerprint)

        if resume or retry_failed:
            self.store.recover_running(task_ids)
            self.store.refresh_missing_outputs(task_ids)
        else:
            self.store.reset_for_new_run(task_ids)

        if retry_failed:
            self.store.retry_failed(task_ids)

        tasks = self.store.pending(task_ids, take=take)
        logger.info("批量任务：本次待处理 %s / 总任务 %s", len(tasks), len(task_ids))
        max_attempts = max(1, int(getattr(self.engine.settings, "batch_retry_attempts", 3)))

        for index, task in enumerate(tasks, 1):
            task_id = int(task["id"])
            logger.info("[%s/%s] %s", index, len(tasks), task["raw_source"])

            for attempt in range(1, max_attempts + 1):
                self.store.mark_running(task_id, stage=f"attempt_{attempt}")
                try:
                    await self._run_one(task, fingerprint)
                    break
                except Exception as exc:
                    code, retryable = classify_error(exc)
                    if retryable and attempt < max_attempts:
                        delay = 1 if attempt == 1 else 5
                        logger.warning(
                            "任务暂时失败 [%s]，%ss 后自动重试 (%s/%s): %s",
                            code, delay, attempt, max_attempts, exc,
                        )
                        await asyncio.sleep(delay)
                        continue
                    self.store.mark_failed(task_id, code, str(exc), retryable=retryable)
                    logger.error(
                        "任务失败 [%s%s]: %s",
                        code, ", retryable" if retryable else "", exc,
                    )
                    break

        return self.store.summary(task_ids)
