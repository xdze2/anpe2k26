"""Disk interface for a single enrichment node.

A node lives at USER_DATA_DIR/nodes/<node_id>/ and contains:
  fetch.jsonl           — append-only state machine log; events: put | fetch_done | summarize_done | …
  summarize/<file>.json — one result file per process run, linked from fetch.jsonl
  summary.md            — current summary, overwritten on each update
  raw_data/<file>       — raw fetch output, one file per completed fetch
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
class FetchEntry:
    uid: str
    tool: str
    target: str


class NodeDir:
    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.path = NODES_DIR / node_id
        self._fetch_file = self.path / "fetch.jsonl"
        self._summary_file = self.path / "summary.md"
        self._raw_dir = self.path / "raw_data"
        self._summarize_dir = self.path / "summarize"

    def exists(self) -> bool:
        return self.path.exists()

    def init(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        self._raw_dir.mkdir(exist_ok=True)
        self._summarize_dir.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Fetch log
    # ------------------------------------------------------------------

    def _append_fetch_event(self, event: dict) -> None:  # type: ignore[type-arg]
        with self._fetch_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def append_target(self, tool: str, target: str) -> str:
        """Append a put event to the fetch log. Returns the new uid."""
        if not self.path.exists():
            self.init()
        uid = _uid()
        self._append_fetch_event(
            {"event": "put", "uid": uid, "tool": tool, "target": target, "ts": _now()}
        )
        return uid

    def _load_fetch_events(self) -> list[dict]:  # type: ignore[type-arg]
        if not self._fetch_file.exists():
            return []
        return [
            json.loads(line)
            for line in self._fetch_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _latest_event_per_uid(self) -> dict[str, dict]:  # type: ignore[type-arg]
        """Return the last event seen for each uid."""
        latest: dict[str, dict] = {}  # type: ignore[type-arg]
        puts: dict[str, dict] = {}  # type: ignore[type-arg]
        for ev in self._load_fetch_events():
            uid = ev.get("uid", "")
            if ev["event"] == "put":
                puts[uid] = ev
            latest[uid] = ev
        return puts, latest

    def pop_pending(self) -> FetchEntry | None:
        """Return the first target in a pending state (put or summarize_error)."""
        puts, latest = self._latest_event_per_uid()
        for uid, put_ev in puts.items():
            last = latest.get(uid, put_ev)
            if last["event"] in ("put", "summarize_error"):
                return FetchEntry(uid=uid, tool=put_ev["tool"], target=put_ev["target"])
        return None

    def get_fetch_done(self, uid: str) -> dict | None:  # type: ignore[type-arg]
        """Return the fetch_done event for a uid, or None."""
        for ev in self._load_fetch_events():
            if ev.get("uid") == uid and ev["event"] == "fetch_done":
                return ev
        return None

    def get_latest_fetch_done(self) -> tuple[FetchEntry, str] | None:
        """Return (FetchEntry, raw_file) for the most recent fetch_done event."""
        puts: dict[str, dict] = {}  # type: ignore[type-arg]
        last_done: dict | None = None  # type: ignore[type-arg]
        for ev in self._load_fetch_events():
            uid = ev.get("uid", "")
            if ev["event"] == "put":
                puts[uid] = ev
            elif ev["event"] == "fetch_done":
                last_done = ev
        if last_done is None:
            return None
        uid = last_done["uid"]
        put_ev = puts.get(uid)
        if put_ev is None:
            return None
        entry = FetchEntry(uid=uid, tool=put_ev["tool"], target=put_ev["target"])
        return entry, last_done["raw_file"]

    def mark_fetch_done(self, entry: FetchEntry, raw_file: str) -> None:
        self._append_fetch_event(
            {"event": "fetch_done", "uid": entry.uid, "raw_file": raw_file, "ts": _now()}
        )

    def mark_fetch_error(self, entry: FetchEntry, detail: str) -> None:
        self._append_fetch_event(
            {"event": "fetch_error", "uid": entry.uid, "detail": detail, "ts": _now()}
        )

    def mark_summarize_done(self, entry: FetchEntry, model: str, status: str, result_file: str) -> None:
        self._append_fetch_event(
            {"event": "summarize_done", "uid": entry.uid,
             "model": model, "status": status, "result_file": result_file, "ts": _now()}
        )

    def mark_summarize_error(self, entry: FetchEntry, detail: str) -> None:
        self._append_fetch_event(
            {"event": "summarize_error", "uid": entry.uid, "detail": detail, "ts": _now()}
        )

    def get_fetch_history(self) -> list[dict]:  # type: ignore[type-arg]
        """Return one summary dict per uid, ordered by put timestamp."""
        puts, latest = self._latest_event_per_uid()
        rows = []
        for uid, put_ev in puts.items():
            last = latest.get(uid, put_ev)
            rows.append({
                "uid": uid,
                "tool": put_ev.get("tool", ""),
                "target": put_ev.get("target", ""),
                "put_ts": put_ev.get("ts", ""),
                "last_event": last["event"],
                "last_ts": last.get("ts", ""),
            })
        return rows

    def save_raw(self, tool: str, target: str, data: str, ext: str = "txt") -> str:
        """Write raw fetch output to raw_data/. Returns the filename."""
        if not self._raw_dir.exists():
            self.init()
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        slug = target[:40].replace("/", "_").replace(" ", "_")
        filename = f"raw_{tool}_{slug}_{ts}.{ext}"
        (self._raw_dir / filename).write_text(data, encoding="utf-8")
        return filename

    # ------------------------------------------------------------------
    # Summarize results
    # ------------------------------------------------------------------

    def prompt_file_path(self, entry: FetchEntry, ts: str) -> Path:
        """Return the path for a prompt debug file (not yet written)."""
        slug = entry.target[:40].replace("/", "_").replace(" ", "_")
        return self._summarize_dir / f"prompt_{entry.tool}_{slug}_{ts}.txt"

    def save_summarize_result(
        self,
        entry: FetchEntry,
        model: str,
        status: str,
        summary: str,
        new_targets: list[tuple[str, str]],
    ) -> str:
        """Write one summarize result file. Returns the filename."""
        if not self._summarize_dir.exists():
            self.init()
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        slug = entry.target[:40].replace("/", "_").replace(" ", "_")
        filename = f"sum_{entry.tool}_{slug}_{status}_{ts}.json"
        data = {
            "ts": _now(),
            "fetch_uid": entry.uid,
            "model": model,
            "status": status,
            "summary": summary,
            "new_targets": [{"tool": t, "target": u} for t, u in new_targets],
        }
        (self._summarize_dir / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return filename

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_summary(self) -> str:
        if not self._summary_file.exists():
            return ""
        return self._summary_file.read_text(encoding="utf-8")

    def save_summary(self, text: str) -> None:
        if not self.path.exists():
            self.init()
        self._summary_file.write_text(text, encoding="utf-8")
