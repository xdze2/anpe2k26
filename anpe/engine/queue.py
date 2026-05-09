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

from anpe.engine.vault import USER_VAULT_DIR

QUEUE_DB = USER_VAULT_DIR / "queue.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT NOT NULL,
    node_id     TEXT,
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
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


@dataclass
class Item:
    uid: str
    node_id: str | None   # None for process-level steps with no associated node
    step: str
    args: dict  # type: ignore[type-arg]


class Queue:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or QUEUE_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def put(self, node_id: str | None, step: str, version: str, args: dict, force: bool = False) -> str:  # type: ignore[type-arg]
        """Enqueue a work item. Returns uid. Idempotent unless force=True."""
        if force:
            import secrets
            args = {**args, "_nonce": secrets.token_hex(4)}
        uid = _content_uid(step, version, args)

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

    def claim(self, step: str, worker_id: str, skip_uids: set[str] | None = None) -> Item | None:
        """Atomically claim one pending item for step. Returns None if nothing claimable.

        skip_uids: UIDs to exclude — used by the runner to avoid re-claiming items
        that already failed with error_retry in this session.
        """
        with self._conn:
            # Find a pending uid: latest event is 'put' or 'error_retry'.
            # Always read args from the original 'put' event row (error_retry has no args).
            if skip_uids:
                placeholders = ",".join("?" * len(skip_uids))
                row = self._conn.execute(
                    f"""
                    SELECT e.uid, e.node_id, put_ev.args
                    FROM events e
                    JOIN events put_ev ON put_ev.uid = e.uid AND put_ev.step = e.step AND put_ev.event = 'put'
                    WHERE e.step = ?
                      AND e.id = (SELECT MAX(id) FROM events WHERE step = ? AND uid = e.uid)
                      AND e.event IN ('put', 'error_retry')
                      AND e.uid NOT IN ({placeholders})
                    LIMIT 1
                    """,
                    (step, step, *skip_uids),
                ).fetchone()
            else:
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

    def mark_done(self, uid: str, step: str, node_id: str | None, outputs: dict) -> None:  # type: ignore[type-arg]
        with self._conn:
            self._conn.execute(
                "INSERT INTO events (uid, node_id, step, event, ts, outputs) VALUES (?,?,?,?,?,?)",
                (uid, node_id, step, "done", _now(), json.dumps(outputs)),
            )

    def mark_error(self, uid: str, step: str, node_id: str | None, reason: str, retryable: bool) -> None:
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

    def counts(self) -> dict[str, dict[str, int]]:
        """Return {step: {event: count}} using each item's latest event."""
        rows = self._conn.execute(
            """
            SELECT step, event, COUNT(*) as n
            FROM events
            WHERE id IN (SELECT MAX(id) FROM events GROUP BY uid)
            GROUP BY step, event
            ORDER BY step, event
            """
        ).fetchall()
        result: dict[str, dict[str, int]] = {}
        for step, event, n in rows:
            result.setdefault(step, {})[event] = n
        return result

    def node_history(self, node_id: str, step: str | None = None) -> list[dict]:  # type: ignore[type-arg]
        """Return all events for node_id ordered by id, optionally filtered by step."""
        if step:
            rows = self._conn.execute(
                "SELECT id, uid, step, event, ts, args, outputs, worker_id, error "
                "FROM events WHERE node_id = ? AND step = ? ORDER BY id",
                (node_id, step),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, uid, step, event, ts, args, outputs, worker_id, error "
                "FROM events WHERE node_id = ? ORDER BY id",
                (node_id,),
            ).fetchall()
        keys = ["id", "uid", "step", "event", "ts", "args", "outputs", "worker_id", "error"]
        return [dict(zip(keys, r)) for r in rows]

    def is_done(self, step: str, version: str, args: dict) -> bool:  # type: ignore[type-arg]
        """Return True if a done event exists for this content-addressed uid."""
        uid = _content_uid(step, version, args)
        row = self._conn.execute(
            "SELECT 1 FROM events WHERE uid = ? AND event = 'done' LIMIT 1", (uid,)
        ).fetchone()
        return row is not None

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

    def done_events(self, step: str, *, newest_first: bool = False) -> list[dict]:  # type: ignore[type-arg]
        """Return all done events for step, each as {uid, node_id, outputs}.

        Default order is oldest-first (lowest id first).
        Pass newest_first=True to get the most recent event at index 0.
        """
        order = "DESC" if newest_first else "ASC"
        rows = self._conn.execute(
            f"SELECT uid, node_id, outputs FROM events WHERE step = ? AND event = 'done' ORDER BY id {order}",
            (step,),
        ).fetchall()
        return [{"uid": r[0], "node_id": r[1], "outputs": r[2]} for r in rows]

    def close(self) -> None:
        self._conn.close()
