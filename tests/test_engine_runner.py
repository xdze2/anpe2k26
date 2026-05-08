"""Tests for the Runner and the scan/put/run/step CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from anpe.cli import cli
from anpe.engine.queue import Queue
from anpe.engine.runner import Runner
from anpe.engine.steps.base import Candidate
from anpe.engine.vault import Vault


# ---------------------------------------------------------------------------
# Minimal fake step for runner tests
# ---------------------------------------------------------------------------

class _OkStep:
    name = "ok_step"
    version = "v1"

    def scan(self, **_: object) -> list[Candidate]:
        return []

    async def work(self, args: dict, vault: Vault, log) -> dict:  # type: ignore[type-arg]
        return {"result": args.get("value", "done")}


class _ErrorStep:
    name = "err_step"
    version = "v1"

    def scan(self, **_: object) -> list[Candidate]:
        return []

    async def work(self, args: dict, vault: Vault, log) -> dict:  # type: ignore[type-arg]
        raise RuntimeError("retryable failure")


class _FatalStep:
    name = "fatal_step"
    version = "v1"

    def scan(self, **_: object) -> list[Candidate]:
        return []

    async def work(self, args: dict, vault: Vault, log) -> dict:  # type: ignore[type-arg]
        raise ValueError("fatal failure")


# ---------------------------------------------------------------------------
# Runner unit tests
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_queue(tmp_path: Path) -> Queue:
    return Queue(db_path=tmp_path / "queue.db")


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Vault:
    return Vault(root=tmp_path / "vault")


@pytest.mark.asyncio
async def test_runner_drains_queue(tmp_queue: Queue, tmp_vault: Vault) -> None:
    step = _OkStep()
    tmp_queue.put("node1", step.name, step.version, {"value": "hello"})
    tmp_queue.put("node2", step.name, step.version, {"value": "world"})

    runner = Runner([step], tmp_queue, tmp_vault)
    results = await runner.run_until_empty(step_name=step.name)

    assert len(results) == 2
    assert all(r.status == "done" for r in results)
    assert {r.node_id for r in results} == {"node1", "node2"}
    assert tmp_queue.pending(step.name) == []


@pytest.mark.asyncio
async def test_runner_retryable_error(tmp_queue: Queue, tmp_vault: Vault) -> None:
    step = _ErrorStep()
    tmp_queue.put("node1", step.name, step.version, {})

    runner = Runner([step], tmp_queue, tmp_vault)
    results = await runner.run_until_empty(step_name=step.name)

    assert len(results) == 1
    assert results[0].status == "error_retry"
    assert "retryable" in results[0].error


@pytest.mark.asyncio
async def test_runner_fatal_error(tmp_queue: Queue, tmp_vault: Vault) -> None:
    step = _FatalStep()
    tmp_queue.put("node1", step.name, step.version, {})

    runner = Runner([step], tmp_queue, tmp_vault)
    results = await runner.run_until_empty(step_name=step.name)

    assert len(results) == 1
    assert results[0].status == "error_abort"
    assert tmp_queue.pending(step.name) == []  # error_abort items do not re-appear


@pytest.mark.asyncio
async def test_runner_budget(tmp_queue: Queue, tmp_vault: Vault) -> None:
    step = _OkStep()
    for i in range(5):
        tmp_queue.put(f"node{i}", step.name, step.version, {"value": str(i)})

    runner = Runner([step], tmp_queue, tmp_vault)
    results = await runner.run_until_empty(step_name=step.name, budget=2)

    assert len(results) == 2


@pytest.mark.asyncio
async def test_runner_empty_queue_returns_immediately(tmp_queue: Queue, tmp_vault: Vault) -> None:
    step = _OkStep()
    runner = Runner([step], tmp_queue, tmp_vault)
    results = await runner.run_until_empty(step_name=step.name)
    assert results == []


# ---------------------------------------------------------------------------
# CLI: anpe scan
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_nodes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anpe.node_dir.NODES_DIR", tmp_path / "nodes")
    monkeypatch.setattr("anpe.engine.steps.fetch_ddg.NODES_DIR", tmp_path / "nodes")
    monkeypatch.setattr("anpe.engine.steps.fetch_ddg.USER_VAULT_DIR", tmp_path / "vault")
    monkeypatch.setattr("anpe.engine.steps.summarize_ddg.NODES_DIR", tmp_path / "nodes")
    monkeypatch.setattr("anpe.engine.steps.eval.NODES_DIR", tmp_path / "nodes")


def test_scan_empty(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "fetch_ddg"])
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_scan_produces_json_lines(tmp_path: Path) -> None:
    nodes_dir = tmp_path / "nodes"
    node_path = nodes_dir / "acme"
    node_path.mkdir(parents=True)
    fetch_file = node_path / "fetch.jsonl"
    fetch_file.write_text(
        json.dumps({"uid": "abc1", "event": "put", "tool": "ddg", "target": "Acme France"}) + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "fetch_ddg"])
    assert result.exit_code == 0
    lines = [l for l in result.output.strip().splitlines() if l]
    assert len(lines) == 1
    candidate = json.loads(lines[0])
    assert candidate["step"] == "fetch_ddg"
    assert candidate["node_id"] == "acme"
    assert candidate["args"]["target"] == "Acme France"


# ---------------------------------------------------------------------------
# CLI: anpe put
# ---------------------------------------------------------------------------

def test_put_reads_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anpe.engine.queue.QUEUE_DB", tmp_path / "queue.db")

    candidate = json.dumps({
        "step": "fetch_ddg",
        "node_id": "acme",
        "args": {"uid": "abc1", "tool": "ddg", "target": "Acme France"},
        "context": {},
    })

    runner = CliRunner()
    result = runner.invoke(cli, ["put"], input=candidate + "\n")
    assert result.exit_code == 0
    assert "queued" in result.output
    assert "1 item(s) queued" in result.output


def test_put_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anpe.engine.queue.QUEUE_DB", tmp_path / "queue.db")

    candidate = json.dumps({
        "step": "fetch_ddg",
        "node_id": "acme",
        "args": {"uid": "abc1", "tool": "ddg", "target": "Acme France"},
        "context": {},
    })
    stdin = candidate + "\n" + candidate + "\n"

    runner = CliRunner()
    result = runner.invoke(cli, ["put"], input=stdin)
    assert result.exit_code == 0
    assert "1 item(s) queued" in result.output
    assert "1 already present" in result.output


# ---------------------------------------------------------------------------
# CLI: anpe scan --help and anpe run --help
# ---------------------------------------------------------------------------

def test_scan_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "--help"])
    assert result.exit_code == 0
    assert "fetch_ddg" in result.output


def test_run_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])
    assert result.exit_code == 0
    assert "--step" in result.output
    assert "--budget" in result.output


def test_step_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["step", "--help"])
    assert result.exit_code == 0
    assert "STEP" in result.output
    assert "--budget" in result.output
