"""Async runner — drains the queue, respects rate limits, recovers stale claims."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from anpe.engine.logger import StepLogger
from anpe.engine.queue import Queue
from anpe.engine.rate_gate import NoGate
from anpe.engine.base import FatalError, RetryableError, Step
from anpe.engine.vault import Vault

CLAIM_TIMEOUT_S = 300
POLL_INTERVAL_S = 0.5


@dataclass
class RunResult:
    uid: str
    node_id: str
    step: str
    status: str          # "done" | "error_retry" | "error_abort"
    outputs: dict = field(default_factory=dict)   # type: ignore[type-arg]
    error: str = ""


class Runner:
    def __init__(
        self,
        steps: list[Step],
        queue: Queue,
        vault: Vault,
        *,
        concurrency: int = 4,
    ) -> None:
        self._steps = {s.name: s for s in steps}
        self._queue = queue
        self._vault = vault
        self._concurrency = concurrency
        self._worker_id = uuid.uuid4().hex[:8]
        self._results: list[RunResult] = []
        self._active: int = 0
        self._lock = asyncio.Lock()
        # UIDs attempted this session — error_retry items are left in the queue
        # for the next run, not retried immediately.
        self._attempted: set[str] = set()

    async def run_until_empty(
        self,
        step_name: str | None = None,
        budget: int | None = None,
    ) -> list[RunResult]:
        """Drain the queue. Optionally restrict to one step and/or a total run budget."""
        names = [step_name] if step_name else list(self._steps)
        tasks = [
            asyncio.create_task(self._worker(name, budget))
            for name in names
            for _ in range(self._concurrency)
        ]
        await asyncio.gather(*tasks)
        return self._results

    async def _worker(self, step_name: str, budget: int | None) -> None:
        step = self._steps.get(step_name)
        if step is None:
            return

        # Recover stale claims once at startup, before entering the claim loop.
        self._sweep_stale(step_name)

        while True:

            async with self._lock:
                if budget is not None and len(self._results) >= budget:
                    return

            async with self._lock:
                skip_uids = set(self._attempted)

            item = self._queue.claim(step_name, self._worker_id, skip_uids=skip_uids)
            if item is None:
                # Queue empty or only items already attempted this session.
                # If no other worker is in-flight, we're done.
                async with self._lock:
                    if self._active == 0:
                        return
                # Another worker is still running; wait in case a stale-claim
                # recovery produces a new claimable item.
                await asyncio.sleep(POLL_INTERVAL_S)
                continue

            async with self._lock:
                self._attempted.add(item.uid)
                self._active += 1

            log_path = self._vault.root / item.node_id / item.step / f"{item.uid[:8]}.log"
            logger = StepLogger(log_path)
            gate = getattr(step, "rate_gate", NoGate())
            try:
                await gate.acquire()
                outputs = await step.work(item.args, self._vault, logger)
                self._queue.mark_done(item.uid, step_name, item.node_id, outputs)
                result = RunResult(
                    uid=item.uid, node_id=item.node_id, step=step_name,
                    status="done", outputs=outputs,
                )
            except asyncio.CancelledError:
                raise
            except RetryableError as e:
                self._queue.mark_error(item.uid, step_name, item.node_id, str(e), retryable=True)
                result = RunResult(
                    uid=item.uid, node_id=item.node_id, step=step_name,
                    status="error_retry", error=str(e),
                )
            except (FatalError, Exception) as e:
                self._queue.mark_error(item.uid, step_name, item.node_id, str(e), retryable=False)
                result = RunResult(
                    uid=item.uid, node_id=item.node_id, step=step_name,
                    status="error_abort", error=str(e),
                )
            finally:
                logger.close()
                async with self._lock:
                    self._active -= 1

            async with self._lock:
                self._results.append(result)

    def _sweep_stale(self, step_name: str) -> None:
        for stale in self._queue.stale_claims(step_name, CLAIM_TIMEOUT_S):
            self._queue.mark_error(stale.uid, step_name, stale.node_id, "claim timeout", retryable=True)
