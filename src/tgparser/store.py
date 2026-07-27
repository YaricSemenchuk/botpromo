"""Local SQLite persistence: idempotency log, retry outbox, per-chat checkpoints.

CRM is idempotent on externalId too (duplicate POST -> {"ok":true,"duplicate":true}),
so this store isn't the only line of defense — it's here for restart-safety
(don't reprocess history we've already seen) and for the retry queue.

sqlite3 connections aren't safe to share across threads without care; since
callers are async code that offloads to threads via asyncio.to_thread, all
public methods here take a lock around their SQL so a single connection can
be reused from any thread.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_messages (
    external_id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    tag TEXT,
    sent_at TEXT,
    http_status INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox (
    external_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    chat_id INTEGER PRIMARY KEY,
    last_message_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class OutboxItem:
    external_id: str
    payload: dict
    attempts: int
    last_error: Optional[str]


class Store:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- idempotency / processed log -------------------------------------

    def is_processed(self, external_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM processed_messages WHERE external_id = ?", (external_id,)
            ).fetchone()
        return row is not None

    def record_processed(
        self,
        external_id: str,
        chat_id: int,
        message_id: int,
        action: str,
        tag: Optional[str],
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR IGNORE INTO processed_messages
                   (external_id, chat_id, message_id, action, tag, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (external_id, chat_id, message_id, action, tag, _now_iso()),
            )
            self._conn.commit()

    def mark_sent(self, external_id: str, http_status: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE processed_messages SET sent_at = ?, http_status = ? WHERE external_id = ?",
                (_now_iso(), http_status, external_id),
            )
            self._conn.commit()

    # -- outbox / retry queue ---------------------------------------------

    def enqueue_outbox(self, external_id: str, payload: dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR IGNORE INTO outbox (external_id, payload_json, attempts, created_at)
                   VALUES (?, ?, 0, ?)""",
                (external_id, json.dumps(payload, ensure_ascii=False), _now_iso()),
            )
            self._conn.commit()

    def ready_outbox_items(self, limit: int = 50) -> list[OutboxItem]:
        now = _now_iso()
        with self._lock:
            rows = self._conn.execute(
                """SELECT external_id, payload_json, attempts, last_error FROM outbox
                   WHERE next_retry_at IS NULL OR next_retry_at <= ?
                   ORDER BY created_at ASC LIMIT ?""",
                (now, limit),
            ).fetchall()
        return [
            OutboxItem(
                external_id=row["external_id"],
                payload=json.loads(row["payload_json"]),
                attempts=row["attempts"],
                last_error=row["last_error"],
            )
            for row in rows
        ]

    def reschedule_outbox(self, external_id: str, next_retry_at_iso: str, error: str) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE outbox SET attempts = attempts + 1, next_retry_at = ?, last_error = ?
                   WHERE external_id = ?""",
                (next_retry_at_iso, error, external_id),
            )
            self._conn.commit()

    def remove_from_outbox(self, external_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM outbox WHERE external_id = ?", (external_id,))
            self._conn.commit()

    # -- per-chat checkpoints (catch-up after restart) --------------------

    def get_checkpoint(self, chat_id: int) -> Optional[int]:
        with self._lock:
            row = self._conn.execute(
                "SELECT last_message_id FROM checkpoints WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        return row["last_message_id"] if row else None

    def set_checkpoint(self, chat_id: int, last_message_id: int) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO checkpoints (chat_id, last_message_id, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(chat_id) DO UPDATE SET
                       last_message_id = excluded.last_message_id,
                       updated_at = excluded.updated_at""",
                (chat_id, last_message_id, _now_iso()),
            )
            self._conn.commit()
