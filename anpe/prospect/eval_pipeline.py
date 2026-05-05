"""Eval pipeline — one LLM scoring per call.

State machine (per node, in eval_queue.jsonl):

    put ──eval──► eval_done        [terminal until next put]
        │
        ├────────► eval_discarded  [terminal — no scorable summary]
        │
        └────────► eval_error      [retryable — pop_eval_pending picks it up again]

State = last event in the file.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from anpe.node_dir import NodeDir
from anpe.prospect.eval import EVAL_VERSION, llm_eval


@dataclass
class EvalStepLog:
    node_id: str
    status: str  # "ok" | "eval_error" | "empty_queue" | "no_profile" | "no_summary"
    score: str = ""
    fit: str = ""


async def eval_step(node_id: str) -> EvalStepLog:
    """Pop one pending eval, run the LLM, write result. Return a log entry."""
    from anpe.profile import active_profile_file

    node = NodeDir(node_id)

    pending = node.pop_eval_pending()
    if pending is None:
        return EvalStepLog(node_id=node_id, status="empty_queue")

    profile_path = active_profile_file()
    if profile_path is None:
        return EvalStepLog(node_id=node_id, status="no_profile")

    sum_file = pending["sum_file"]
    profile_file = str(profile_path)

    sum_path = node.path / sum_file
    if not sum_path.exists():
        node.mark_eval_error(f"sum_file not found: {sum_file}")
        return EvalStepLog(node_id=node_id, status="eval_error")

    import json
    sum_data = json.loads(sum_path.read_text(encoding="utf-8"))
    summary = sum_data.get("summary", "")
    if not summary:
        node.mark_eval_discarded(f"no summary in {sum_file}")
        return EvalStepLog(node_id=node_id, status="no_summary")

    profile_text = profile_path.read_text(encoding="utf-8")

    print(f"[{node_id}] eval  score against {profile_path.name}")
    try:
        t0 = time.monotonic()
        result = await llm_eval(summary, profile_text)
        duration_s = round(time.monotonic() - t0, 2)
    except Exception as e:
        detail = str(e)
        print(f"[{node_id}] eval  ERROR: {detail}")
        node.mark_eval_error(detail)
        return EvalStepLog(node_id=node_id, status="eval_error")

    print(f"[{node_id}] eval  score={result.score!r}  fit={result.fit!r}")

    result_file = node.save_eval_result(
        sum_file=sum_file,
        profile_file=profile_file,
        eval_version=EVAL_VERSION,
        model="mistral-small-2603",
        score=result.score,
        fit=result.fit,
        dealbreakers=result.dealbreakers,
        uncertainty=result.uncertainty,
        duration_s=duration_s,
    )
    node.mark_eval_done(result_file)

    return EvalStepLog(node_id=node_id, status="ok", score=result.score, fit=result.fit)


async def run_eval_batch(
    node_ids: list[str],
    budget: int | None,
) -> AsyncGenerator[EvalStepLog, None]:
    """Run eval steps across nodes, one at a time.

    budget: total steps across all nodes (None = unlimited).
    """
    budget_remaining = budget
    for node_id in node_ids:
        while True:
            log = await eval_step(node_id)
            yield log
            if log.status == "empty_queue":
                break
            if budget_remaining is not None:
                budget_remaining -= 1
                if budget_remaining <= 0:
                    return
