from __future__ import annotations

import itertools
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Iterator

from anpe.engine.types import Candidate, FatalError, Log, RetryableError
from anpe.engine.vault import Vault


@contextmanager
def log_appender(vault: Vault, node_id: str | None) -> Generator[Log, None, None]:
    if node_id is not None:
        log_path = vault.root / "nodes" / node_id / "node.log"
    else:
        log_path = vault.root / "node.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch()

    def append(msg: str) -> None:
        with log_path.open("a") as f:
            f.write(msg + "\n")

    yield append


def run_step(step: object, vault: Vault, do_max: int | None, **flags: object) -> tuple[int, int]:
    """Run scan→work loop. Returns (ran, skipped)."""
    candidates: Iterator[Candidate] = step.scan(vault, **flags)  # type: ignore[union-attr]
    if do_max is not None:
        candidates = itertools.islice(candidates, do_max)
    ran = skipped = 0
    for candidate in candidates:
        with log_appender(vault, candidate.node_id) as log:
            try:
                step.work(candidate.args, vault, log)  # type: ignore[union-attr]
                ran += 1
            except FatalError as e:
                log(f"fatal: {e}")
                skipped += 1
            except RetryableError as e:
                log(f"retry: {e}")
                skipped += 1
    return ran, skipped
