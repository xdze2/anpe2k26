"""Enrichment pipeline — one fetch→eval cycle per call.

State machine (per uid in fetch.jsonl):

    put ──fetch──► fetch_done ──summarize──► summarize_done          (ok | no_data)
         │                   │                   └─ enqueues new_targets
         │                   └────────────► summarize_not_relevant  (not_relevant)
         │                                      └─ no new_targets enqueued
         ▼
    fetch_error | not_found | blocked | retryable   [terminal / manual retry]

summarize_error is a retryable state: pop_pending will pick it up again
(fetch is skipped — raw data already on disk).
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from anpe.node_dir import FetchEntry, NodeDir
from anpe.prospect.errors import FetchBlockedError, FetchNotFoundError, FetchRetryableError
from anpe.prospect.registry import FETCH_TOOLS


@dataclass
class StepLog:
    node_id: str
    tool: str
    target: str
    # "ok" | "not_relevant" | "no_data"
    # | "not_found" | "retryable" | "blocked"
    # | "fetch_error" | "summarize_error" | "empty_queue"
    status: str
    new_targets: list[tuple[str, str]] = field(default_factory=list)


async def enrich_step(node_id: str) -> StepLog:
    """Pop one pending target, fetch if needed, then process. Return a log entry."""
    node = NodeDir(node_id)

    entry = node.pop_pending()
    if entry is None:
        print(f"[{node_id}] queue is empty")
        return StepLog(node_id=node_id, tool="", target="", status="empty_queue")

    # Check if fetch is already done (summarize_error retry or resummarize case)
    fetch_done_ev = node.get_fetch_done(entry.uid)
    if fetch_done_ev is not None:
        raw_file = fetch_done_ev["raw_file"]
        raw_data = (node._raw_dir / raw_file).read_text(encoding="utf-8")
        print(f"[{node_id}] fetch  already done, re-running process (uid={entry.uid})")
    else:
        print(f"[{node_id}] fetch  [{entry.tool}] {entry.target!r}  (uid={entry.uid})")
        raw_data, error, fetch_status = _fetch(entry)

        if raw_data is None:
            print(f"[{node_id}] fetch  {fetch_status}: {error}")
            node.mark_fetch_error(entry, error or fetch_status or "unknown")
            return StepLog(node_id=node_id, tool=entry.tool, target=entry.target,
                           status=fetch_status or "fetch_error")

        print(f"[{node_id}] fetch  ok  ({len(raw_data)} chars)")
        ext = FETCH_TOOLS[entry.tool].raw_ext
        raw_file = node.save_raw(entry.tool, entry.target, raw_data, ext=ext)
        node.mark_fetch_done(entry, raw_file)

    return await _run_process(node, entry, raw_data, raw_file)



async def _run_process(node: NodeDir, entry: FetchEntry, raw_data: str, raw_file: str) -> StepLog:
    tool = FETCH_TOOLS.get(entry.tool)
    if tool is None:
        node.mark_summarize_error(entry, f"unknown tool: {entry.tool!r}")
        return StepLog(node_id=node.node_id, tool=entry.tool, target=entry.target,
                       status="summarize_error")

    previous_summary = node.get_latest_summary()
    print(f"[{node.node_id}] process  [{entry.tool}]  (previous: {len(previous_summary)} chars)")

    try:
        t0 = time.monotonic()
        company_profile = _fmt_company_profile(node.get_siren_meta())
        result = await tool.summarize(raw_data, previous_summary, company_profile)
        duration_s = round(time.monotonic() - t0, 2)
    except Exception as e:
        detail = str(e)
        print(f"[{node.node_id}] process  ERROR: {detail}")
        node.mark_summarize_error(entry, detail)
        return StepLog(node_id=node.node_id, tool=entry.tool, target=entry.target,
                       status="summarize_error")

    print(f"[{node.node_id}] process  status={result.status!r}"
          f"  new_targets={len(result.new_targets)}")

    new_targets = [(t.tool, t.target) for t in result.new_targets]
    result_file = node.save_summarize_result(
        entry=entry,
        model=result.model,
        summarize_version=result.version,
        status=result.status,
        summary=result.summary,
        new_targets=new_targets,
        raw_file=raw_file,
        prompt=result.prompt,
        duration_s=duration_s,
    )
    node.mark_summarize_done(
        entry, result_file=result_file,
        not_relevant=(result.status == "not_relevant"),
    )

    if result.status == "not_relevant":
        return StepLog(node_id=node.node_id, tool=entry.tool, target=entry.target,
                       status="not_relevant", new_targets=new_targets)

    for tool_slug, target in new_targets:
        if tool_slug in FETCH_TOOLS:
            node.append_target(tool_slug, target)

    if result.status == "ok":
        from anpe.profile import active_profile_file
        profile_path = active_profile_file()
        if profile_path is not None:
            node.append_eval_put(
                sum_file=f"summarize/{result_file}",
                profile_file=str(profile_path),
            )

    return StepLog(node_id=node.node_id, tool=entry.tool, target=entry.target,
                   status=result.status, new_targets=new_targets)


def _fetch(entry: FetchEntry) -> tuple[str, None, None] | tuple[None, str, str]:
    tool = FETCH_TOOLS.get(entry.tool)
    if tool is None:
        return None, f"unknown tool: {entry.tool!r}", "fetch_error"
    try:
        return tool.fetch(entry.target), None, None
    except FetchNotFoundError as e:
        return None, str(e), "not_found"
    except FetchRetryableError as e:
        return None, str(e), "retryable"
    except FetchBlockedError as e:
        return None, str(e), "blocked"
    except Exception as e:
        return None, str(e), "fetch_error"


def _fmt_company_profile(fm: dict) -> str:  # type: ignore[type-arg]
    """Format frontmatter fields as the 'Company profile' block for the LLM prompt."""
    keys = ["name", "siren", "naf", "category", "headcount", "city"]
    lines = [f"{k.capitalize()}: {fm[k]}" for k in keys if k in fm]
    return "\n".join(lines)


async def run_batch(
    node_ids: list[str],
    budget: int | None,
) -> AsyncGenerator[StepLog, None]:
    """Run nodes depth-first.

    budget: total steps across all nodes (None = unlimited).
    Stops immediately on blocked.
    """
    budget_remaining = budget
    for node_id in node_ids:
        while True:
            log = await enrich_step(node_id)
            yield log
            if log.status == "blocked":
                return
            if log.status in ("empty_queue", "not_found"):
                break
            if budget_remaining is not None:
                budget_remaining -= 1
                if budget_remaining <= 0:
                    return
