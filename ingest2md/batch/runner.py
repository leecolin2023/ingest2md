"""Serial, resumable batch runner built on the same IngestionEngine as single mode."""
from __future__ import annotations

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

        for index, task in enumerate(tasks, 1):
            task_id = int(task["id"])
            self.store.mark_running(task_id)
            logger.info("[%s/%s] %s", index, len(tasks), task["raw_source"])
            try:
                result = await self.engine.ingest_one(IngestionRequest(
                    source=task["raw_source"],
                    name=task["name"],
                    tags=tuple(__import__("json").loads(task["tags_json"] or "[]")),
                ))
                self.store.mark_success(task_id, result)
                logger.info("已保存: %s", result.output_path)
            except Exception as exc:
                code, retryable = classify_error(exc)
                self.store.mark_failed(task_id, code, str(exc))
                logger.error("任务失败 [%s%s]: %s", code, ", retryable" if retryable else "", exc)

        return self.store.summary(task_ids)
