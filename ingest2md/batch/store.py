"""SQLite-backed resumable batch task state."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ingest2md.engine import IngestionRequest, IngestionResult, task_identity
from ingest2md.batch.models import StoredTask


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TaskStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_key TEXT NOT NULL,
                task_key TEXT NOT NULL,
                config_fingerprint TEXT NOT NULL,
                raw_source TEXT NOT NULL,
                normalized_source TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                source_type TEXT NOT NULL DEFAULT '',
                source_id TEXT NOT NULL DEFAULT '',
                canonical_key TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                stage TEXT NOT NULL DEFAULT '',
                attempts INTEGER NOT NULL DEFAULT 0,
                output_path TEXT NOT NULL DEFAULT '',
                error_code TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                retryable INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT '',
                finished_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE(batch_key, task_key, config_fingerprint)
            )
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def prepare(self, batch_key: str, requests: list[IngestionRequest],
                fingerprint: str, *, resume: bool) -> None:
        now = _now()
        for request in requests:
            normalized, task_key = task_identity(request.source)
            row = self.db.execute(
                "SELECT * FROM tasks WHERE batch_key=? AND task_key=? AND config_fingerprint=?",
                (batch_key, task_key, fingerprint),
            ).fetchone()
            if row is None:
                self.db.execute(
                    """
                    INSERT INTO tasks (
                        batch_key, task_key, config_fingerprint, raw_source, normalized_source,
                        name, tags_json, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        batch_key, task_key, fingerprint, request.source, normalized,
                        request.name, json.dumps(request.tags, ensure_ascii=False), now, now,
                    ),
                )
                continue

            if resume:
                status = row["status"]
                output_path = row["output_path"]
                if status == "running" or (
                    status == "success" and output_path and not Path(output_path).exists()
                ):
                    self.db.execute(
                        """
                        UPDATE tasks SET status='pending', stage='', error_code='',
                            error_message='', retryable=0, updated_at=?
                        WHERE id=?
                        """,
                        (now, row["id"]),
                    )
            else:
                self.db.execute(
                    """
                    UPDATE tasks SET raw_source=?, normalized_source=?, name=?, tags_json=?,
                        status='pending', stage='', attempts=0, output_path='',
                        error_code='', error_message='', retryable=0,
                        started_at='', finished_at='', updated_at=?
                    WHERE id=?
                    """,
                    (
                        request.source, normalized, request.name,
                        json.dumps(request.tags, ensure_ascii=False), now, row["id"],
                    ),
                )
        self.db.commit()

    def selected(self, batch_key: str, fingerprint: str, *,
                 retry_failed: bool = False, take: int = 0) -> list[StoredTask]:
        status = "failed" if retry_failed else "pending"
        sql = (
            "SELECT * FROM tasks WHERE batch_key=? AND config_fingerprint=? AND status=? "
            "ORDER BY id"
        )
        params: list[object] = [batch_key, fingerprint, status]
        if take:
            sql += " LIMIT ?"
            params.append(take)
        rows = self.db.execute(sql, params).fetchall()
        return [
            StoredTask(
                id=row["id"],
                raw_source=row["raw_source"],
                normalized_source=row["normalized_source"],
                name=row["name"],
                tags=tuple(json.loads(row["tags_json"] or "[]")),
                status=row["status"],
                attempts=row["attempts"],
            )
            for row in rows
        ]

    def mark_running(self, task_id: int) -> None:
        now = _now()
        self.db.execute(
            """
            UPDATE tasks SET status='running', stage='ingesting',
                attempts=attempts+1, started_at=?, finished_at='', updated_at=?
            WHERE id=?
            """,
            (now, now, task_id),
        )
        self.db.commit()

    def mark_result(self, task_id: int, result: IngestionResult) -> None:
        now = _now()
        self.db.execute(
            """
            UPDATE tasks SET status=?, stage='', source_type=?, source_id=?,
                canonical_key=?, output_path=?, error_code=?, error_message=?,
                retryable=?, finished_at=?, updated_at=?
            WHERE id=?
            """,
            (
                result.status,
                result.source_type,
                result.source_id,
                result.canonical_key,
                str(result.output_path or ""),
                result.error_code,
                result.error_message[:4000],
                int(result.retryable),
                now,
                now,
                task_id,
            ),
        )
        self.db.commit()

    def summary(self, batch_key: str, fingerprint: str) -> dict[str, int]:
        rows = self.db.execute(
            """
            SELECT status, COUNT(*) AS count FROM tasks
            WHERE batch_key=? AND config_fingerprint=?
            GROUP BY status
            """,
            (batch_key, fingerprint),
        ).fetchall()
        counts = {row["status"]: row["count"] for row in rows}
        counts["total"] = sum(counts.values())
        return counts
