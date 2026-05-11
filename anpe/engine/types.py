from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


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
