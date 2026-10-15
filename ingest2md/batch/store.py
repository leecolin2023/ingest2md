"""SQLite-backed durable state for batch ingestion."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ingest2md.batch.models import BatchItem, BatchSummary, task_identity
from ingest2md.engine import IngestionResult


class TaskStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.db.close()

    def _init_schema(self) -> None:
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_source TEXT NOT NULL,
                normalized_source TEXT NOT NULL,
                task_key TEXT NOT NULL,
                config_fingerprint TEXT NOT NULL,
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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                finished_at TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_key, config_fingerprint)
            )
        """)
        self.db.commit()

    def register(self, items: list[BatchItem], fingerprint: str) -> list[int]:
        ids = []
        for item in items:
            normalized, task_key = task_identity(item.source)
            self.db.execute(
                """
                INSERT OR IGNORE INTO tasks (
                    raw_source, normalized_source, task_key, config_fingerprint,
                    name, tags_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.source, normalized, task_key, fingerprint, item.name,
                    json.dumps(item.tags, ensure_ascii=False),
                ),
            )
            row = self.db.execute(
                "SELECT id FROM tasks WHERE task_key=? AND config_fingerprint=?",
                (task_key, fingerprint),
            ).fetchone()
            ids.append(int(row["id"]))
        self.db.commit()
        return list(dict.fromkeys(ids))

    def reset_for_new_run(self, ids: list[int]) -> None:
        if not ids:
            return
        sql, params = self._in_clause(ids)
        self.db.execute(
            f"""UPDATE tasks
                SET status='pending', stage='', attempts=0, output_path='',
                    source_type='', source_id='', canonical_key='',
                    error_code='', error_message='', started_at=NULL, finished_at=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id IN ({sql})""",
            params,
        )
        self.db.commit()

    def recover_running(self, ids: list[int]) -> None:
        if not ids:
            return
        sql, params = self._in_clause(ids)
        self.db.execute(
            f"""UPDATE tasks SET status='pending', stage='',
                updated_at=CURRENT_TIMESTAMP
                WHERE id IN ({sql}) AND status='running'""",
            params,
        )
        self.db.commit()

    def retry_failed(self, ids: list[int]) -> None:
        if not ids:
            return
        sql, params = self._in_clause(ids)
        self.db.execute(
            f"""UPDATE tasks SET status='pending', stage='', error_code='',
                error_message='', finished_at=NULL, updated_at=CURRENT_TIMESTAMP
                WHERE id IN ({sql}) AND status='failed'""",
            params,
        )
        self.db.commit()

    def refresh_missing_outputs(self, ids: list[int]) -> None:
        if not ids:
            return
        sql, params = self._in_clause(ids)
        rows = self.db.execute(
            f"SELECT id, output_path FROM tasks WHERE id IN ({sql}) AND status='success'",
            params,
        ).fetchall()
        stale = [
            int(row["id"]) for row in rows
            if not row["output_path"] or not Path(row["output_path"]).exists()
        ]
        if stale:
            sql2, params2 = self._in_clause(stale)
            self.db.execute(
                f"""UPDATE tasks SET status='pending', output_path='',
                    updated_at=CURRENT_TIMESTAMP WHERE id IN ({sql2})""",
                params2,
            )
            self.db.commit()

    def pending(self, ids: list[int], take: int = 0) -> list[sqlite3.Row]:
        if not ids:
            return []
        sql, params = self._in_clause(ids)
        query = f"SELECT * FROM tasks WHERE id IN ({sql}) AND status='pending' ORDER BY id"
        if take > 0:
            query += " LIMIT ?"
            params = [*params, take]
        return self.db.execute(query, params).fetchall()

    def mark_running(self, task_id: int, stage: str = "ingesting") -> None:
        self.db.execute(
            """UPDATE tasks SET status='running', stage=?, attempts=attempts+1,
               started_at=CURRENT_TIMESTAMP, finished_at=NULL,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (stage, task_id),
        )
        self.db.commit()

    def mark_success(self, task_id: int, result: IngestionResult) -> None:
        self.db.execute(
            """UPDATE tasks SET status='success', stage='done', source_type=?,
               source_id=?, canonical_key=?, output_path=?, error_code='',
               error_message='', finished_at=CURRENT_TIMESTAMP,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (
                result.source_type, result.source_id, result.canonical_key,
                str(result.output_path), task_id,
            ),
        )
        self.db.commit()

    def mark_failed(self, task_id: int, code: str, message: str) -> None:
        self.db.execute(
            """UPDATE tasks SET status='failed', stage='', error_code=?,
               error_message=?, finished_at=CURRENT_TIMESTAMP,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (code, message[:4000], task_id),
        )
        self.db.commit()

    def summary(self, ids: list[int]) -> BatchSummary:
        if not ids:
            return BatchSummary(0, 0, 0, 0, 0)
        sql, params = self._in_clause(ids)
        rows = self.db.execute(
            f"""SELECT status, COUNT(*) AS count FROM tasks
                WHERE id IN ({sql}) GROUP BY status""",
            params,
        ).fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return BatchSummary(
            total=len(ids),
            success=counts.get("success", 0),
            failed=counts.get("failed", 0),
            pending=counts.get("pending", 0),
            running=counts.get("running", 0),
        )

    @staticmethod
    def _in_clause(ids: list[int]) -> tuple[str, list[int]]:
        return ",".join("?" for _ in ids), list(ids)
