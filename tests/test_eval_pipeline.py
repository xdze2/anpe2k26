"""Tests for anpe/prospect/eval_pipeline.py."""

import json
import pytest
from pathlib import Path
from pydantic_ai.models.test import TestModel

import anpe.profile as profile_mod
from anpe.node_dir import NodeDir
from anpe.prospect.eval import _agent
from anpe.prospect.eval_pipeline import eval_step, run_eval_batch


@pytest.fixture(autouse=True)
def patch_nodes(tmp_path, monkeypatch):
    monkeypatch.setattr("anpe.node_dir.NODES_DIR", tmp_path / "nodes")
    monkeypatch.setattr(profile_mod, "_USER_DATA_DIR", tmp_path)


def _make_node(tmp_path: Path, node_id: str, summary: str = "A great PME.") -> NodeDir:
    node = NodeDir(node_id)
    node.init()
    # Write a fake sum file
    sum_data = {"summary": summary, "status": "ok"}
    sum_file = "summarize/sum_ddg_test_ok_20260505T120000.json"
    (node._summarize_dir / "sum_ddg_test_ok_20260505T120000.json").write_text(
        json.dumps(sum_data), encoding="utf-8"
    )
    # Write a profile file
    profile_path = tmp_path / "profile_20260505T1200.md"
    profile_path.write_text("Looking for small PME, no ESN.\n", encoding="utf-8")
    # Enqueue eval
    node.append_eval_put(sum_file, str(profile_path))
    return node


@pytest.mark.asyncio
async def test_eval_step_empty_queue(tmp_path):
    node = NodeDir("empty_node")
    node.init()
    log = await eval_step("empty_node")
    assert log.status == "empty_queue"


@pytest.mark.asyncio
async def test_eval_step_no_profile(tmp_path):
    node = NodeDir("no_profile_node")
    node.init()
    node.append_eval_put("summarize/sum_foo.json", "../../profile_20260505T1200.md")
    # No profile file written — active_profile_file() returns None
    log = await eval_step("no_profile_node")
    assert log.status == "no_profile"


@pytest.mark.asyncio
async def test_eval_step_ok(tmp_path):
    node = _make_node(tmp_path, "acme")
    with _agent.override(model=TestModel(custom_output_args={
        "score": "good",
        "fit": "small team, clean product",
        "dealbreakers": [],
        "uncertainty": "low",
    })):
        log = await eval_step("acme")

    assert log.status == "ok"
    assert log.score == "good"
    assert log.fit == "small team, clean product"

    # Result file written
    result = node.get_latest_eval_result()
    assert result is not None
    assert result["score"] == "good"

    # Queue shows eval_done
    assert node.pop_eval_pending() is None


@pytest.mark.asyncio
async def test_eval_step_missing_sum_file(tmp_path):
    profile_path = tmp_path / "profile_20260505T1200.md"
    profile_path.write_text("Looking for small PME.\n", encoding="utf-8")
    node = NodeDir("broken_node")
    node.init()
    node.append_eval_put("summarize/nonexistent.json", str(profile_path))

    log = await eval_step("broken_node")
    assert log.status == "eval_error"
    # Still pending (retryable)
    assert node.pop_eval_pending() is not None


@pytest.mark.asyncio
async def test_run_eval_batch_budget(tmp_path):
    _make_node(tmp_path, "node1")
    _make_node(tmp_path, "node2")

    logs = []
    with _agent.override(model=TestModel(custom_output_args={
        "score": "maybe", "fit": "uncertain domain",
        "dealbreakers": [], "uncertainty": "medium",
    })):
        async for log in run_eval_batch(["node1", "node2"], budget=1):
            logs.append(log)

    ok_logs = [l for l in logs if l.status == "ok"]
    assert len(ok_logs) == 1
