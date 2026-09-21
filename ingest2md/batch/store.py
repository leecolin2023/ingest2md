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
                retryable INTEGER NOT NULL DEFAULT 0,
                duplicate_of_task_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                finished_at TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_key, config_fingerprint)
            )
        """)
        columns = {
            row["name"] for row in self.db.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "retryable" not in columns:
            self.db.execute(
                "ALTER TABLE tasks ADD COLUMN retryable INTEGER NOT NULL DEFAULT 0"
            )
        if "duplicate_of_task_id" not in columns:
            self.db.execute(
                "ALTER TABLE tasks ADD COLUMN duplicate_of_task_id INTEGER"
            )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_canonical "
            "ON tasks(canonical_key, config_fingerprint, status)"
        )
        self.db.commit()

    def register(self, items: list[BatchItem], fingerprint: str) -> list[int]:
        ids = []
        for item in items:
            normalized, task_key = task_identity(item.source)
            self.db.execute(
                """
                INSERT INTO tasks (
                    raw_source, normalized_source, task_key, config_fingerprint,
                    name, tags_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_key, config_fingerprint) DO UPDATE SET
                    raw_source=excluded.raw_source,
                    normalized_source=excluded.normalized_source,
                    status=CASE
                        WHEN tasks.name<>excluded.name OR tasks.tags_json<>excluded.tags_json
                        THEN 'pending' ELSE tasks.status END,
                    stage=CASE
                        WHEN tasks.name<>excluded.name OR tasks.tags_json<>excluded.tags_json
                        THEN '' ELSE tasks.stage END,
                    name=excluded.name,
                    tags_json=excluded.tags_json,
                    updated_at=CURRENT_TIMESTAMP
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
                    error_code='', error_message='', retryable=0,
                    duplicate_of_task_id=NULL,
                    started_at=NULL, finished_at=NULL,
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
                error_message='', retryable=0, finished_at=NULL,
                updated_at=CURRENT_TIMESTAMP
                WHERE id IN ({sql}) AND status='failed'""",
            params,
        )
        self.db.commit()

    def refresh_missing_outputs(self, ids: list[int]) -> None:
        if not ids:
            return
        sql, params = self._in_clause(ids)
        rows = self.db.execute(
            f"""SELECT id, output_path FROM tasks
                WHERE id IN ({sql}) AND status IN ('success', 'duplicate')""",
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
                    duplicate_of_task_id=NULL, updated_at=CURRENT_TIMESTAMP
                    WHERE id IN ({sql2})""",
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
               started_at=COALESCE(started_at, CURRENT_TIMESTAMP),
               finished_at=NULL, retryable=0,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (stage, task_id),
        )
        self.db.commit()

    def set_identity(
        self,
        task_id: int,
        canonical_key: str,
        source_type: str = "",
        source_id: str = "",
    ) -> None:
        self.db.execute(
            """UPDATE tasks SET canonical_key=?, source_type=?, source_id=?,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (canonical_key, source_type, source_id, task_id),
        )
        self.db.commit()

    def find_completed_by_canonical(
        self,
        canonical_key: str,
        fingerprint: str,
        *,
        exclude_task_id: int,
    ) -> sqlite3.Row | None:
        if not canonical_key:
            return None
        rows = self.db.execute(
            """SELECT * FROM tasks
               WHERE canonical_key=? AND config_fingerprint=? AND id<>?
                 AND status IN ('success', 'duplicate')
               ORDER BY CASE status WHEN 'success' THEN 0 ELSE 1 END, id""",
            (canonical_key, fingerprint, exclude_task_id),
        ).fetchall()
        for row in rows:
            if row["output_path"] and Path(row["output_path"]).exists():
                return row
        return None

    def mark_duplicate(self, task_id: int, existing: sqlite3.Row) -> None:
        self.db.execute(
            """UPDATE tasks SET status='duplicate', stage='done',
               canonical_key=?, source_type=?, source_id=?, output_path=?,
               duplicate_of_task_id=?, error_code='', error_message='',
               retryable=0, finished_at=CURRENT_TIMESTAMP,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (
                existing["canonical_key"], existing["source_type"],
                existing["source_id"], existing["output_path"],
                int(existing["id"]), task_id,
            ),
        )
        self.db.commit()

    def mark_success(self, task_id: int, result: IngestionResult) -> None:
        self.db.execute(
            """UPDATE tasks SET status='success', stage='done', source_type=?,
               source_id=?, canonical_key=?, output_path=?, error_code='',
               error_message='', retryable=0, duplicate_of_task_id=NULL,
               finished_at=CURRENT_TIMESTAMP,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (
                result.source_type, result.source_id, result.canonical_key,
                str(result.output_path), task_id,
            ),
        )
        self.db.commit()

    def mark_failed(
        self,
        task_id: int,
        code: str,
        message: str,
        retryable: bool = False,
    ) -> None:
        self.db.execute(
            """UPDATE tasks SET status='failed', stage='', error_code=?,
               error_message=?, retryable=?, finished_at=CURRENT_TIMESTAMP,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (code, message[:4000], int(bool(retryable)), task_id),
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
            duplicate=counts.get("duplicate", 0),
        )

    def status_report(self) -> dict:
        rows = self.db.execute(
            "SELECT status, COUNT(*) AS count FROM tasks GROUP BY status"
        ).fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        errors = self.db.execute(
            """SELECT error_code, COUNT(*) AS count FROM tasks
               WHERE status='failed' GROUP BY error_code ORDER BY count DESC"""
        ).fetchall()
        total = sum(counts.values())
        attempts = self.db.execute(
            "SELECT COALESCE(SUM(attempts), 0) AS total FROM tasks"
        ).fetchone()
        return {
            "total": total,
            "counts": counts,
            "errors": {
                (row["error_code"] or "failed"): int(row["count"]) for row in errors
            },
            "attempts": int(attempts["total"]),
        }

    @staticmethod
    def _in_clause(ids: list[int]) -> tuple[str, list[int]]:
        return ",".join("?" for _ in ids), list(ids)
