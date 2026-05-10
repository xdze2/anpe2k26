"""RateGate — enforces a minimum interval between consecutive calls to an external resource."""

from __future__ import annotations

import asyncio


class BudgetExhausted(Exception):
    """Raised by RateGate.acquire() when the per-session budget for this gate is spent."""

    def __init__(self, gate_name: str) -> None:
        self.gate_name = gate_name
        super().__init__(f"budget exhausted for gate '{gate_name}'")


class RateGate:
    """Serializes callers and enforces a minimum interval between requests.

    The lock ensures only one caller proceeds at a time. Any caller that
    arrives while another is inside acquire() waits, then sleeps for the
    remaining interval before proceeding. This prevents thundering-herd
    retries when multiple workers share the same rate-limited resource.

    An optional per-session budget can be set via set_budget(). Once the
    budget reaches zero, all further acquire() calls raise BudgetExhausted.
    """

    def __init__(self, min_interval_s: float, name: str = "") -> None:
        self._min_interval = min_interval_s
        self._name = name
        self._lock = asyncio.Lock()
        self._last_call: float = 0.0
        self._remaining: int | None = None  # None = unlimited

    def set_budget(self, n: int) -> None:
        """Set the maximum number of acquire() calls allowed this session."""
        self._remaining = n

    async def acquire(self) -> None:
        async with self._lock:
            if self._remaining is not None:
                if self._remaining <= 0:
                    raise BudgetExhausted(self._name)
                self._remaining -= 1
            loop = asyncio.get_event_loop()
            now = loop.time()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = loop.time()


class NoGate:
    """No-op gate for steps with no external rate limit (pure I/O, local ops)."""

    async def acquire(self) -> None:
        pass
