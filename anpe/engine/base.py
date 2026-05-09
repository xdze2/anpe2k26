"""Core types for the data engine step interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterator, Protocol


class RetryableError(Exception):
    """Step failed transiently; the item will be retried in the next run."""


class FatalError(Exception):
    """Step failed permanently; the item will not be retried."""

from anpe.engine.queue import Queue
from anpe.engine.rate_gate import NoGate, RateGate
from anpe.engine.vault import Vault

Log = Callable[[str], None]


@dataclass
class Candidate:
    step: str
    node_id: str | None   # None for process-level steps with no associated node
    args: dict  # type: ignore[type-arg]   — vault URIs + scalar params the work fn needs
    context: dict = field(default_factory=dict)  # type: ignore[type-arg]  — signals for filtering, not stored in queue


class Step(Protocol):
    name: str
    version: str
    description: str
    rate_gate: RateGate | NoGate

    def scan(self, queue: Queue, vault: Vault, **filter_flags: object) -> Iterator[Candidate]: ...

    async def work(self, args: dict, vault: Vault, log: Log) -> dict: ...  # type: ignore[type-arg]
