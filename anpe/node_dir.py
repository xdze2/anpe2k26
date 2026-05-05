"""Disk interface for a single prospect node.

A node lives at USER_DATA_DIR/nodes/<node_id>/ and contains:
  fetch.jsonl           — append-only state machine log; events: put | fetch_done | summarize_done | summarize_not_relevant | …
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
        self._eval_queue_file = self.path / "eval_queue.jsonl"
        self._eval_results_dir = self.path / "eval_results"

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
        """Return the first target in a pending state (put, summarize_error, or resummarize)."""
        puts, latest = self._latest_event_per_uid()
        for uid, put_ev in puts.items():
            last = latest.get(uid, put_ev)
            if last["event"] in ("put", "summarize_error", "resummarize"):
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

    def mark_summarize_done(self, entry: FetchEntry, result_file: str, not_relevant: bool = False) -> None:
        event = "summarize_not_relevant" if not_relevant else "summarize_done"
        self._append_fetch_event(
            {"event": event, "uid": entry.uid, "result_file": result_file, "ts": _now()}
        )

    def mark_summarize_error(self, entry: FetchEntry, detail: str) -> None:
        self._append_fetch_event(
            {"event": "summarize_error", "uid": entry.uid, "detail": detail, "ts": _now()}
        )

    def mark_resummarize(self, uid: str, reason: str = "") -> None:
        """Append a resummarize event — signals the uid needs re-summarizing."""
        ev: dict = {"event": "resummarize", "uid": uid, "ts": _now()}  # type: ignore[type-arg]
        if reason:
            ev["reason"] = reason
        self._append_fetch_event(ev)

    def get_latest_sum_file(self) -> str | None:
        """Return the result_file from the most recent summarize_done event, or None."""
        latest_sum_file = None
        for ev in self._load_fetch_events():
            if ev.get("event") == "summarize_done":
                latest_sum_file = ev.get("result_file")
        return latest_sum_file

    def get_stale_summarize_uids(self, tool_versions: dict[str, str]) -> list[str]:
        """Return uids with a summarize_done whose summarize_version differs from the tool's current version."""
        puts, latest = self._latest_event_per_uid()
        stale = []
        for uid, last in latest.items():
            if last["event"] != "summarize_done":
                continue
            result_file = last.get("result_file", "")
            if not result_file:
                continue
            tool = puts.get(uid, {}).get("tool", "")
            current_version = tool_versions.get(tool)
            if current_version is None:
                continue
            sum_path = self._summarize_dir / result_file
            if not sum_path.exists():
                stale.append(uid)
                continue
            data = json.loads(sum_path.read_text(encoding="utf-8"))
            if data.get("summarize_version") != current_version:
                stale.append(uid)
        return stale

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

    def save_summarize_result(
        self,
        entry: FetchEntry,
        model: str,
        summarize_version: str,
        status: str,
        summary: str,
        new_targets: list[tuple[str, str]],
        raw_file: str,
        prompt: str = "",
        duration_s: float | None = None,
    ) -> str:
        """Write sum_*.json and prompt_*.txt. Returns the json filename."""
        if not self._summarize_dir.exists():
            self.init()
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        slug = entry.target[:40].replace("/", "_").replace(" ", "_")
        stem = f"{entry.tool}_{slug}_{status}_{ts}"
        if prompt:
            (self._summarize_dir / f"prompt_{stem}.txt").write_text(prompt, encoding="utf-8")
        filename = f"sum_{stem}.json"
        data = {
            "ts": _now(),
            "fetch_uid": entry.uid,
            "raw_file": raw_file,
            "model": model,
            "summarize_version": summarize_version,
            "status": status,
            "duration_s": duration_s,
            "summary": summary,
            "new_targets": [{"tool": t, "target": u} for t, u in new_targets],
        }
        (self._summarize_dir / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return filename

    # ------------------------------------------------------------------
    # Summary (frontmatter + body)
    # ------------------------------------------------------------------

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[str, str]:
        """Split '---\\n...\\n---\\nbody' into (frontmatter_block, body).

        Returns ("", text) if no frontmatter is present.
        """
        if not text.startswith("---\n"):
            return "", text
        end = text.find("\n---\n", 4)
        if end == -1:
            return "", text
        return text[4:end], text[end + 5:]

    def get_frontmatter(self) -> dict:  # type: ignore[type-arg]
        """Return parsed YAML frontmatter, or {} if none."""
        import yaml
        if not self._summary_file.exists():
            return {}
        raw = self._summary_file.read_text(encoding="utf-8")
        fm, _ = self._split_frontmatter(raw)
        return yaml.safe_load(fm) or {} if fm else {}

    def set_frontmatter(self, data: dict) -> None:  # type: ignore[type-arg]
        """Merge data into frontmatter, preserving the existing body."""
        import yaml
        if self._summary_file.exists():
            raw = self._summary_file.read_text(encoding="utf-8")
            existing_fm, body = self._split_frontmatter(raw)
            current = yaml.safe_load(existing_fm) or {} if existing_fm else {}
        else:
            current, body = {}, ""
        current.update(data)
        self._write_summary(current, body)

    def get_summary_body(self) -> str:
        """Return only the markdown body (no frontmatter)."""
        if not self._summary_file.exists():
            return ""
        raw = self._summary_file.read_text(encoding="utf-8")
        _, body = self._split_frontmatter(raw)
        return body

    def save_summary(self, body: str) -> None:
        """Overwrite the body, preserving existing frontmatter."""
        import yaml
        if self._summary_file.exists():
            raw = self._summary_file.read_text(encoding="utf-8")
            existing_fm, _ = self._split_frontmatter(raw)
            fm = yaml.safe_load(existing_fm) or {} if existing_fm else {}
        else:
            fm = {}
        if not self.path.exists():
            self.init()
        self._write_summary(fm, body)

    # ------------------------------------------------------------------
    # Reviews log
    # ------------------------------------------------------------------

    def append_review(self, reaction: str) -> None:
        """Append a review event. Empty reaction = skip."""
        event: dict = {"ts": _now()}  # type: ignore[type-arg]
        if reaction:
            event["reaction"] = reaction
        else:
            event["skip"] = True
        review_file = self.path / "reviews.jsonl"
        with review_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def get_latest_review(self) -> dict | None:  # type: ignore[type-arg]
        """Return the last review event, or None."""
        review_file = self.path / "reviews.jsonl"
        if not review_file.exists():
            return None
        all_lines = review_file.read_text(encoding="utf-8").splitlines()
        lines = [line for line in all_lines if line.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])

    def is_reviewed(self) -> bool:
        """True if the latest review is a reaction (not a skip)."""
        ev = self.get_latest_review()
        return ev is not None and not ev.get("skip", False)

    def has_summarize_done(self) -> bool:
        """True if any fetch cycle reached summarize_done (excludes not_relevant)."""
        for ev in self._load_fetch_events():
            if ev.get("event") == "summarize_done":
                return True
        return False

    def _write_summary(self, fm: dict, body: str) -> None:  # type: ignore[type-arg]
        import yaml
        if not self.path.exists():
            self.init()
        if fm:
            text = f"---\n{yaml.dump(fm, allow_unicode=True, sort_keys=False)}---\n{body}"
        else:
            text = body
        self._summary_file.write_text(text, encoding="utf-8")


    # ------------------------------------------------------------------
    # Eval queue
    # ------------------------------------------------------------------

    def _append_eval_event(self, event: dict) -> None:  # type: ignore[type-arg]
        with self._eval_queue_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def _last_eval_event(self) -> dict | None:  # type: ignore[type-arg]
        if not self._eval_queue_file.exists():
            return None
        lines = [
            line for line in self._eval_queue_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return json.loads(lines[-1]) if lines else None

    def append_eval_put(self, sum_file: str, profile_file: str) -> None:
        """Enqueue a node for eval (or re-eval after profile update)."""
        self._append_eval_event(
            {"event": "put", "sum_file": sum_file, "profile_file": profile_file, "ts": _now()}
        )

    def mark_eval_done(self, result_file: str) -> None:
        self._append_eval_event(
            {"event": "eval_done", "result_file": result_file, "ts": _now()}
        )

    def mark_eval_error(self, detail: str) -> None:
        self._append_eval_event(
            {"event": "eval_error", "detail": detail, "ts": _now()}
        )

    def pop_eval_pending(self) -> dict | None:  # type: ignore[type-arg]
        """Return the last eval queue event if the node is pending eval, else None.

        Pending = last event is 'put' or 'eval_error'.
        """
        last = self._last_eval_event()
        if last is None or last["event"] not in ("put", "eval_error"):
            return None
        return last

    def get_latest_eval_result(self) -> dict | None:  # type: ignore[type-arg]
        """Return the parsed JSON of the most recent eval_done result, or None."""
        last = self._last_eval_event()
        if last is None or last["event"] != "eval_done":
            return None
        result_file = last.get("result_file", "")
        if not result_file:
            return None
        path = self._eval_results_dir / Path(result_file).name
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_eval_result(
        self,
        sum_file: str,
        profile_file: str,
        eval_version: str,
        model: str,
        score: str,
        fit: str,
        dealbreakers: list[str],
        uncertainty: str,
        duration_s: float,
    ) -> str:
        """Write eval_results/eval_<ts>_<slug>.json. Returns the filename."""
        if not self._eval_results_dir.exists():
            self._eval_results_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        slug = self.node_id[:40]
        filename = f"eval_{ts}_{slug}.json"
        data = {
            "ts": _now(),
            "sum_file": sum_file,
            "profile_file": profile_file,
            "eval_version": eval_version,
            "model": model,
            "score": score,
            "fit": fit,
            "dealbreakers": dealbreakers,
            "uncertainty": uncertainty,
            "duration_s": duration_s,
        }
        (self._eval_results_dir / filename).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return filename

    def is_eval_stale(self, current_profile_file: str, current_eval_version: str) -> bool:
        """True if the latest eval used a different profile or eval_version."""
        result = self.get_latest_eval_result()
        if result is None:
            return True
        return (
            result.get("profile_file") != current_profile_file
            or result.get("eval_version") != current_eval_version
        )


def all_node_ids_by_ctime() -> list[str]:
    """Return all node ids sorted by directory creation time (oldest first)."""
    if not NODES_DIR.exists():
        return []
    dirs = sorted(NODES_DIR.iterdir(), key=lambda p: p.stat().st_ctime)
    return [p.name for p in dirs if p.is_dir()]
