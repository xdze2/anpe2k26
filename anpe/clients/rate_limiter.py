"""Callable wrapper that enforces a minimum interval between calls."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class RateLimiter(Callable[P, R]):  # type: ignore[misc]
    """Wrap a callable and sleep as needed to enforce a minimum interval."""

    def __init__(self, fn: Callable[P, R], min_interval_s: float) -> None:
        self._fn = fn
        self._min_interval = min_interval_s
        self._last_call: float = 0.0

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        gap = self._min_interval - (time.monotonic() - self._last_call)
        if gap > 0:
            time.sleep(gap)
        try:
            return self._fn(*args, **kwargs)
        finally:
            self._last_call = time.monotonic()
