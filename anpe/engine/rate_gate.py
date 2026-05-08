"""RateGate — enforces a minimum interval between consecutive calls to an external resource."""

from __future__ import annotations

import asyncio


class RateGate:
    """Serializes callers and enforces a minimum interval between requests.

    The lock ensures only one caller proceeds at a time. Any caller that
    arrives while another is inside acquire() waits, then sleeps for the
    remaining interval before proceeding. This prevents thundering-herd
    retries when multiple workers share the same rate-limited resource.
    """

    def __init__(self, min_interval_s: float) -> None:
        self._min_interval = min_interval_s
        self._lock = asyncio.Lock()
        self._last_call: float = 0.0

    async def acquire(self) -> None:
        async with self._lock:
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
