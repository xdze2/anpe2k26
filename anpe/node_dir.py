"""Disk interface for a single enrichment node.

A node lives at USER_DATA_DIR/nodes/<node_id>/ and contains:
  queue.jsonl  — append-only event log; events: put | done | error
  summary.md   — current summary text, overwritten on each update
  raw_*.txt    — raw fetch output, one file per completed fetch
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

USER_DATA_DIR = Path(__file__).parent.parent / "user_data"
NODES_DIR = USER_DATA_DIR / "nodes"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return secrets.token_hex(4)


@dataclass
class QueueEntry:
    uid: str
    tool: str
    target: str


class NodeDir:
    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.path = NODES_DIR / node_id
        self._queue_file = self.path / "queue.jsonl"
        self._summary_file = self.path / "summary.md"

    def exists(self) -> bool:
        return self.path.exists()

    def init(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)

    def _append_event(self, event: dict) -> None:  # type: ignore[type-arg]
        with self._queue_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def append_target(self, tool: str, target: str) -> str:
        """Append a put event. Returns the new uid."""
        if not self.path.exists():
            self.init()
        uid = _uid()
        self._append_event({"event": "put", "uid": uid, "tool": tool, "target": target, "ts": _now()})
        return uid

    def pop_pending(self) -> QueueEntry | None:
        """Return the first uid that has a put but no done/error event."""
        if not self._queue_file.exists():
            return None

        puts: dict[str, dict] = {}  # type: ignore[type-arg]
        closed: set[str] = set()

        for line in self._queue_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            uid = data.get("uid", "")
            if data["event"] == "put":
                puts[uid] = data
            elif data["event"] in ("done", "error"):
                closed.add(uid)

        for uid, data in puts.items():
            if uid not in closed:
                return QueueEntry(uid=uid, tool=data["tool"], target=data["target"])
        return None

    def mark_done(self, entry: QueueEntry, raw_file: str) -> None:
        self._append_event({"event": "done", "uid": entry.uid, "raw_file": raw_file, "ts": _now()})

    def mark_error(self, entry: QueueEntry, detail: str) -> None:
        self._append_event({"event": "error", "uid": entry.uid, "detail": detail, "ts": _now()})

    def save_raw(self, tool: str, target: str, data: str) -> str:
        """Write raw fetch data to a file. Returns the filename."""
        if not self.path.exists():
            self.init()
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        slug = target[:40].replace("/", "_").replace(" ", "_")
        filename = f"raw_{tool}_{slug}_{ts}.txt"
        (self.path / filename).write_text(data, encoding="utf-8")
        return filename

    def get_summary(self) -> str:
        if not self._summary_file.exists():
            return ""
        return self._summary_file.read_text(encoding="utf-8")

    def save_summary(self, text: str) -> None:
        if not self.path.exists():
            self.init()
        self._summary_file.write_text(text, encoding="utf-8")
