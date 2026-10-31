"""Call records plus a transactional outbox for CRM notifications.

The call row and the outbox row are written in one transaction, so a CRM outage
can delay a notification but never lose it.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    call_id     TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL,
    disposition TEXT NOT NULL,
    attempt     INTEGER NOT NULL CHECK (attempt >= 0),
    received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS crm_outbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id      TEXT NOT NULL UNIQUE REFERENCES calls(call_id),
    account_id   TEXT NOT NULL,
    next_call_at TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SENT')),
    tries        INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_outbox_pending ON crm_outbox(status, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str):
        self.path = path
        conn = self._connect()
        try:
            conn.executescript(SCHEMA)
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        # One short-lived connection per operation: safe across threads and workers.
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _tx(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    def ping(self) -> None:
        with self._tx() as conn:
            conn.execute("SELECT 1")

    def record_call(self, call_id: str, account_id: str, disposition: str, attempt: int,
                    next_call_at: datetime | None) -> bool:
        """Returns False if this call_id was already recorded (webhook redelivery)."""
        with self._tx() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO calls (call_id, account_id, disposition, attempt, received_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (call_id, account_id, disposition, attempt, _now()),
            )
            if cur.rowcount == 0:
                return False
            if next_call_at is not None:
                conn.execute(
                    "INSERT INTO crm_outbox (call_id, account_id, next_call_at, updated_at) VALUES (?, ?, ?, ?)",
                    (call_id, account_id, next_call_at.isoformat(), _now()),
                )
            return True

    def pending(self, limit: int = 100) -> list[tuple[int, str, str]]:
        with self._tx() as conn:
            return conn.execute(
                "SELECT id, account_id, next_call_at FROM crm_outbox WHERE status = 'PENDING' ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()

    def mark_sent(self, outbox_id: int) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE crm_outbox SET status = 'SENT', tries = tries + 1, last_error = NULL, updated_at = ? WHERE id = ?",
                (_now(), outbox_id),
            )

    def mark_failed(self, outbox_id: int, error: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE crm_outbox SET tries = tries + 1, last_error = ?, updated_at = ? WHERE id = ?",
                (error[:500], _now(), outbox_id),
            )
