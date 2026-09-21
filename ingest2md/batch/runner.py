"""Serial, resumable batch runner built on the same IngestionEngine as single mode."""
from __future__ import annotations

import logging

from ingest2md.batch.store import TaskStore
from ingest2md.engine import IngestionEngine, IngestionRequest

logger = logging.getLogger(__name__)


class BatchRunner:
    def __init__(self, engine: IngestionEngine, store: TaskStore,
                 batch_key: str, config_fingerprint: str):
        self.engine = engine
        self.store = store
        self.batch_key = batch_key
        self.config_fingerprint = config_fingerprint

    async def run(self, requests: list[IngestionRequest], *, resume: bool = False,
                  retry_failed: bool = False, take: int = 0) -> dict[str, int]:
        self.store.prepare(
            self.batch_key,
            requests,
            self.config_fingerprint,
            resume=resume or retry_failed,
        )
        tasks = self.store.selected(
            self.batch_key,
            self.config_fingerprint,
            retry_failed=retry_failed,
            take=take,
        )
        for index, task in enumerate(tasks, 1):
            logger.info(
                "批量任务 [%s/%s] %s",
                index, len(tasks), task.name or task.raw_source,
            )
            self.store.mark_running(task.id)
            result = await self.engine.ingest_one(IngestionRequest(
                source=task.raw_source,
                name=task.name,
                tags=task.tags,
            ))
            self.store.mark_result(task.id, result)
            if result.status == "success":
                logger.info("批量任务完成: %s", result.output_path)
            else:
                logger.error(
                    "批量任务失败 [%s]: %s",
                    result.error_code or "ingestion_failed",
                    result.error_message,
                )
        return self.store.summary(self.batch_key, self.config_fingerprint)
