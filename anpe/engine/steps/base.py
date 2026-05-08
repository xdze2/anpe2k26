"""Core types for the data engine step interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from anpe.engine.queue import Queue
from anpe.engine.vault import Vault

Log = Callable[[str], None]


@dataclass
class Candidate:
    step: str
    node_id: str
    args: dict  # type: ignore[type-arg]   — vault URIs + scalar params the work fn needs
    context: dict = field(default_factory=dict)  # type: ignore[type-arg]  — signals for filtering, not stored in queue


class Step(Protocol):
    name: str
    version: str
    description: str

    def scan(self, queue: Queue, **filter_flags: object) -> list[Candidate]: ...

    async def work(self, args: dict, vault: Vault, log: Log) -> dict: ...  # type: ignore[type-arg]
