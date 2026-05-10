"""Sync runner — serial execution of SyncStep items."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from anpe.engine.base import FatalError, RetryableError, SyncStep
from anpe.engine.logger import StepLogger
from anpe.engine.queue import Queue
from anpe.engine.vault import Vault


@dataclass
class SyncRunResult:
    uid: str
    node_id: str | None
    step: str
    status: str          # "done" | "error_retry" | "error_abort"
    outputs: dict = field(default_factory=dict)   # type: ignore[type-arg]
    error: str = ""


class SyncRunner:
    def __init__(self, step: SyncStep, queue: Queue, vault: Vault) -> None:
        self._step = step
        self._queue = queue
        self._vault = vault
        self._worker_id = uuid.uuid4().hex[:8]

    def run_until_empty(self, budget: int | None = None) -> list[SyncRunResult]:
        """Drain the queue serially. Stops early if budget items are processed."""
        step_name = self._step.name
        results: list[SyncRunResult] = []
        attempted: set[str] = set()

        self._sweep_stale(step_name)

        while True:
            if budget is not None and len(results) >= budget:
                break

            item = self._queue.claim(step_name, self._worker_id, skip_uids=attempted)
            if item is None:
                break

            attempted.add(item.uid)

            if item.node_id is not None:
                log_path = self._vault.root / item.step / item.node_id / f"{item.uid[:8]}.log"
            else:
                log_path = self._vault.root / item.step / f"{item.uid[:8]}.log"
            logger = StepLogger(log_path)

            result: SyncRunResult | None = None
            try:
                outputs = self._step.work(item.args, self._vault, logger)
                self._queue.mark_done(item.uid, step_name, item.node_id, outputs)
                result = SyncRunResult(
                    uid=item.uid, node_id=item.node_id, step=step_name,
                    status="done", outputs=outputs,
                )
            except RetryableError as e:
                self._queue.mark_error(item.uid, step_name, item.node_id, str(e), retryable=True)
                result = SyncRunResult(
                    uid=item.uid, node_id=item.node_id, step=step_name,
                    status="error_retry", error=str(e),
                )
            except FatalError:
                self._queue.mark_error(item.uid, step_name, item.node_id, "user quit", retryable=True)
                break
            except Exception as e:
                self._queue.mark_error(item.uid, step_name, item.node_id, str(e), retryable=False)
                result = SyncRunResult(
                    uid=item.uid, node_id=item.node_id, step=step_name,
                    status="error_abort", error=str(e),
                )
            finally:
                logger.close()

            if result is not None:
                results.append(result)

        return results

    def _sweep_stale(self, step_name: str) -> None:
        from anpe.engine.runner import CLAIM_TIMEOUT_S
        for stale in self._queue.stale_claims(step_name, CLAIM_TIMEOUT_S):
            self._queue.mark_error(stale.uid, step_name, stale.node_id, "claim timeout", retryable=True)
