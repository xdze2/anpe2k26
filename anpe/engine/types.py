from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Callable
from typing import Protocol, runtime_checkable


class RetryableError(Exception):
    """Step failed transiently; the item will be retried in the next run."""


class FatalError(Exception):
    """Step failed permanently; the item will not be retried."""


Log = Callable[[str], None]


@dataclass
class Candidate:
    node_id: str | None  # None for process-level steps with no associated node
    args: dict = field(default_factory=dict)  # type: ignore[type-arg]
    skip: bool = False  # already done; run_step counts it but does not call work()


@runtime_checkable
class Step(Protocol):
    """Contract for all pipeline steps.

    scan() yields ALL candidates — both pending and already-done.
    Already-done candidates have skip=True; run_step counts them but does not
    call work(). do_max is applied only to the non-skipped candidates, so
    skipped items never consume work slots.

    work() performs the actual work for one candidate. It should raise
    FatalError for permanent failures (no retry) or RetryableError for
    transient ones. Other exceptions propagate and abort the run.
    """

    name: str

    def scan(self, vault: "Vault", **flags: object) -> Iterator[Candidate]: ...  # type: ignore[name-defined]  # noqa: F821

    def work(self, args: dict, vault: "Vault", log: Log) -> None: ...  # type: ignore[name-defined]  # noqa: F821
