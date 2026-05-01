"""Disk interface for a single enrichment node.

A node lives at USER_DATA_DIR/nodes/<node_id>/ and contains:
  queue.jsonl  — append-only, one JSON object per line
  summary.md   — current summary text, overwritten on each update
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

USER_DATA_DIR = Path(__file__).parent.parent / "user_data"
NODES_DIR = USER_DATA_DIR / "nodes"


@dataclass
class QueueEntry:
    tool: str
    target: str
    status: str  # "pending" | "done" | "error"
    ts: str


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

    def append_target(self, tool: str, target: str) -> None:
        if not self.path.exists():
            self.init()
        entry = QueueEntry(
            tool=tool,
            target=target,
            status="pending",
            ts=datetime.now(timezone.utc).isoformat(),
        )
        with self._queue_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.__dict__) + "\n")

    def pop_pending(self) -> QueueEntry | None:
        """Return the first pending entry without mutating the file."""
        if not self._queue_file.exists():
            return None
        for line in self._queue_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("status") == "pending":
                return QueueEntry(**data)
        return None

    def mark_entry(self, entry: QueueEntry, status: str) -> None:
        """Rewrite queue.jsonl updating the first matching pending entry."""
        if not self._queue_file.exists():
            return
        lines = self._queue_file.read_text(encoding="utf-8").splitlines()
        updated = False
        new_lines: list[str] = []
        for line in lines:
            if not line.strip():
                continue
            data = json.loads(line)
            if (
                not updated
                and data.get("status") == "pending"
                and data.get("tool") == entry.tool
                and data.get("target") == entry.target
            ):
                data["status"] = status
                updated = True
            new_lines.append(json.dumps(data))
        self._queue_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    def get_summary(self) -> str:
        if not self._summary_file.exists():
            return ""
        return self._summary_file.read_text(encoding="utf-8")

    def save_summary(self, text: str) -> None:
        if not self.path.exists():
            self.init()
        self._summary_file.write_text(text, encoding="utf-8")

    def list_queue(self) -> list[QueueEntry]:
        if not self._queue_file.exists():
            return []
        entries = []
        for line in self._queue_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(QueueEntry(**json.loads(line)))
        return entries
