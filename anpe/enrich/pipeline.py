"""One step of the enrichment loop."""

from __future__ import annotations

from dataclasses import dataclass

from anpe.enrich.registry import FETCH_TOOLS
from anpe.enrich.summarize import llm_summarize
from anpe.node_dir import NodeDir, QueueEntry


@dataclass
class StepLog:
    node_id: str
    tool: str
    target: str
    status: str       # "ok" | "not_relevant" | "no_data" | "fetch_error" | "empty_queue"
    new_targets: list[tuple[str, str]]


async def enrich_step(node_id: str) -> StepLog:
    """Pop one pending target, fetch it, summarize, save. Return a log entry."""
    node = NodeDir(node_id)

    entry = node.pop_pending()
    if entry is None:
        print(f"[{node_id}] queue is empty")
        return StepLog(node_id=node_id, tool="", target="", status="empty_queue", new_targets=[])

    print(f"[{node_id}] fetch  [{entry.tool}] {entry.target!r}")
    raw_data = _fetch(entry)
    if raw_data is None:
        print(f"[{node_id}] fetch  ERROR")
        node.mark_entry(entry, "error")
        return StepLog(node_id=node_id, tool=entry.tool, target=entry.target,
                       status="fetch_error", new_targets=[])

    print(f"[{node_id}] fetch  ok  ({len(raw_data)} chars)")
    node.save_raw(entry.tool, entry.target, raw_data)

    previous_summary = node.get_summary()
    print(f"[{node_id}] llm    summarize  (previous summary: {len(previous_summary)} chars)")
    result = await llm_summarize(raw_data, previous_summary)
    print(f"[{node_id}] llm    status={result.status!r}  new_targets={len(result.new_targets)}")

    node.mark_entry(entry, "done")

    if result.status == "not_relevant":
        return StepLog(node_id=node_id, tool=entry.tool, target=entry.target,
                       status="not_relevant", new_targets=[])

    node.save_summary(result.summary)

    new_targets = [(t.tool, t.target) for t in result.new_targets]
    for tool, target in new_targets:
        if tool in FETCH_TOOLS:
            node.append_target(tool, target)

    return StepLog(node_id=node_id, tool=entry.tool, target=entry.target,
                   status=result.status, new_targets=new_targets)


def _fetch(entry: QueueEntry) -> str | None:
    fetch_fn = FETCH_TOOLS.get(entry.tool)
    if fetch_fn is None:
        print(f"  unknown tool: {entry.tool!r}")
        return None
    try:
        return fetch_fn(entry.target)
    except Exception as e:
        print(f"  exception: {e}")
        return None
