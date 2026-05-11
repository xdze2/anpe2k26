from __future__ import annotations

from pathlib import Path

import pytest

from anpe.engine.run_step import run_step
from anpe.engine.types import Candidate, FatalError, RetryableError
from anpe.engine.vault import Vault


class _MockStep:
    def __init__(self, candidates: list[Candidate], side_effect: Exception | None = None) -> None:
        self._candidates = candidates
        self._side_effect = side_effect
        self.calls: list[dict] = []  # type: ignore[type-arg]

    def scan(self, vault: Vault, **flags: object):
        return iter(self._candidates)

    def work(self, args: dict, vault: Vault, log) -> None:  # type: ignore[type-arg]
        self.calls.append(args)
        if self._side_effect is not None:
            raise self._side_effect


def test_run_step_counts_and_log_created(tmp_path: Path) -> None:
    vault = Vault(root=tmp_path)
    candidates = [
        Candidate(node_id="aaa111", args={"x": 1}),
        Candidate(node_id="bbb222", args={"x": 2}),
    ]
    step = _MockStep(candidates)

    ran, skipped = run_step(step, vault, do_max=None)

    assert ran == 2
    assert skipped == 0
    assert len(step.calls) == 2
    assert (tmp_path / "nodes" / "aaa111" / "node.log").exists()
    assert (tmp_path / "nodes" / "bbb222" / "node.log").exists()


def test_run_step_do_max_limits_candidates(tmp_path: Path) -> None:
    vault = Vault(root=tmp_path)
    candidates = [Candidate(node_id=f"n{i}", args={}) for i in range(5)]
    step = _MockStep(candidates)

    ran, skipped = run_step(step, vault, do_max=2)

    assert ran == 2
    assert len(step.calls) == 2


def test_run_step_fatal_error_counts_as_skipped(tmp_path: Path) -> None:
    vault = Vault(root=tmp_path)
    candidates = [Candidate(node_id="x1", args={})]
    step = _MockStep(candidates, side_effect=FatalError("boom"))

    ran, skipped = run_step(step, vault, do_max=None)

    assert ran == 0
    assert skipped == 1
    log_text = (tmp_path / "nodes" / "x1" / "node.log").read_text()
    assert "fatal: boom" in log_text


def test_run_step_retryable_error_counts_as_skipped(tmp_path: Path) -> None:
    vault = Vault(root=tmp_path)
    candidates = [Candidate(node_id="x2", args={})]
    step = _MockStep(candidates, side_effect=RetryableError("transient"))

    ran, skipped = run_step(step, vault, do_max=None)

    assert ran == 0
    assert skipped == 1
    log_text = (tmp_path / "nodes" / "x2" / "node.log").read_text()
    assert "retry: transient" in log_text


def test_run_step_process_level_node_log(tmp_path: Path) -> None:
    vault = Vault(root=tmp_path)
    candidates = [Candidate(node_id=None, args={})]
    step = _MockStep(candidates)

    ran, skipped = run_step(step, vault, do_max=None)

    assert ran == 1
    assert (tmp_path / "node.log").exists()
