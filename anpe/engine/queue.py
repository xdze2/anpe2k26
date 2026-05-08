"""Concurrency-safe work queue backed by a SQLite append-only event log.

Item identity is content-addressed: uid = sha256(step + version + args).
put() is idempotent — inserting the same (step, version, args) twice is a no-op.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

USER_VAULT_DIR = Path(__file__).parent.parent.parent / "user_vault"
QUEUE_DB = USER_VAULT_DIR / "queue.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT NOT NULL,
    node_id     TEXT NOT NULL,
    step        TEXT NOT NULL,
    event       TEXT NOT NULL,
    ts          TEXT NOT NULL,
    args        TEXT,
    outputs     TEXT,
    worker_id   TEXT,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_step_uid ON events (step, uid, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_uid(step: str, version: str, args: dict) -> str:  # type: ignore[type-arg]
    payload = json.dumps({"step": step, "version": version, "args": args}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Item:
    uid: str
    node_id: str
    step: str
    args: dict  # type: ignore[type-arg]


class Queue:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or QUEUE_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def put(self, node_id: str, step: str, version: str, args: dict, force: bool = False) -> str:  # type: ignore[type-arg]
        """Enqueue a work item. Returns uid. Idempotent unless force=True."""
        uid = _content_uid(step, version, args)
        if force:
            # perturb uid so this is treated as a distinct item
            import secrets
            uid = uid + secrets.token_hex(4)

        with self._conn:
            # Check if this uid already has any event — if so, skip.
            row = self._conn.execute(
                "SELECT 1 FROM events WHERE uid = ? LIMIT 1", (uid,)
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO events (uid, node_id, step, event, ts, args) VALUES (?,?,?,?,?,?)",
                    (uid, node_id, step, "put", _now(), json.dumps(args)),
                )
        return uid

    def claim(self, step: str, worker_id: str) -> Item | None:
        """Atomically claim one pending item for step. Returns None if queue is empty."""
        with self._conn:
            # Find a pending uid: latest event is 'put' or 'error_retry'.
            # Always read args from the original 'put' event row (error_retry has no args).
            row = self._conn.execute(
                """
                SELECT e.uid, e.node_id, put_ev.args
                FROM events e
                JOIN events put_ev ON put_ev.uid = e.uid AND put_ev.step = e.step AND put_ev.event = 'put'
                WHERE e.step = ?
                  AND e.id = (SELECT MAX(id) FROM events WHERE step = ? AND uid = e.uid)
                  AND e.event IN ('put', 'error_retry')
                LIMIT 1
                """,
                (step, step),
            ).fetchone()
            if row is None:
                return None
            uid, node_id, args_json = row
            self._conn.execute(
                "INSERT INTO events (uid, node_id, step, event, ts, worker_id) VALUES (?,?,?,?,?,?)",
                (uid, node_id, step, "claimed", _now(), worker_id),
            )
        return Item(uid=uid, node_id=node_id, step=step, args=json.loads(args_json))

    def mark_done(self, uid: str, step: str, node_id: str, outputs: dict) -> None:  # type: ignore[type-arg]
        with self._conn:
            self._conn.execute(
                "INSERT INTO events (uid, node_id, step, event, ts, outputs) VALUES (?,?,?,?,?,?)",
                (uid, node_id, step, "done", _now(), json.dumps(outputs)),
            )

    def mark_error(self, uid: str, step: str, node_id: str, reason: str, retryable: bool) -> None:
        event = "error_retry" if retryable else "error_abort"
        with self._conn:
            self._conn.execute(
                "INSERT INTO events (uid, node_id, step, event, ts, error) VALUES (?,?,?,?,?,?)",
                (uid, node_id, step, event, _now(), reason),
            )

    def pending(self, step: str) -> list[Item]:
        """Return all items whose latest event is 'put' or 'error_retry'."""
        rows = self._conn.execute(
            """
            SELECT e.uid, e.node_id, put_ev.args
            FROM events e
            JOIN events put_ev ON put_ev.uid = e.uid AND put_ev.event = 'put'
            WHERE e.step = ?
              AND e.id = (SELECT MAX(id) FROM events WHERE step = ? AND uid = e.uid)
              AND e.event IN ('put', 'error_retry')
            ORDER BY e.id
            """,
            (step, step),
        ).fetchall()
        return [Item(uid=r[0], node_id=r[1], step=step, args=json.loads(r[2])) for r in rows]

    def stale_claims(self, step: str, older_than_s: int = 300) -> list[Item]:
        """Return items claimed but not finished within older_than_s seconds."""
        rows = self._conn.execute(
            """
            SELECT e.uid, e.node_id, put_ev.args
            FROM events e
            JOIN events put_ev ON put_ev.uid = e.uid AND put_ev.step = e.step AND put_ev.event = 'put'
            WHERE e.step = ?
              AND e.id = (SELECT MAX(id) FROM events WHERE step = ? AND uid = e.uid)
              AND e.event = 'claimed'
              AND (unixepoch('now') - unixepoch(e.ts)) >= ?
            """,
            (step, step, older_than_s),
        ).fetchall()
        return [Item(uid=r[0], node_id=r[1], step=step, args=json.loads(r[2])) for r in rows]

    def close(self) -> None:
        self._conn.close()
