"""Per-run step logger — writes timestamped lines to a file in the vault."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M.%S")


class StepLogger:
    """Accumulates log lines then flushes to a vault path when closed."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._buf = io.StringIO()

    def __call__(self, msg: str) -> None:
        self._buf.write(f"{_now()}  {msg}\n")

    def close(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(self._buf.getvalue(), encoding="utf-8")
