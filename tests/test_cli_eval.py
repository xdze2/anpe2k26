"""Smoke tests for 'anpe prospect eval' and 'anpe prospect reeval' CLI commands."""

import json
import pytest
from click.testing import CliRunner
from pathlib import Path
from pydantic_ai.models.test import TestModel

import anpe.profile as profile_mod
from anpe.node_dir import NodeDir
from anpe.prospect.eval import _agent
from anpe.cli import cli


@pytest.fixture(autouse=True)
def patch_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr("anpe.node_dir.NODES_DIR", tmp_path / "nodes")
    monkeypatch.setattr(profile_mod, "_USER_DATA_DIR", tmp_path)


SUM_FILE = "sum_ddg_test_ok_20260505T120000.json"


def _make_summarized_node(tmp_path: Path, node_id: str) -> NodeDir:
    """Node with a summarize_done in fetch.jsonl but no eval queue entry."""
    node = NodeDir(node_id)
    node.init()
    sum_data = {"summary": "A good PME.", "status": "ok"}
    (node._summarize_dir / SUM_FILE).write_text(json.dumps(sum_data), encoding="utf-8")
    # Simulate a summarize_done event in fetch.jsonl
    from anpe.node_dir import FetchEntry
    entry = FetchEntry(uid="aabbccdd", tool="ddg", target="Acme France")
    node.mark_fetch_done(entry, f"raw_ddg_acme.json")
    node.mark_summarize_done(entry, result_file=SUM_FILE)
    return node


def _make_eval_ready_node(tmp_path: Path, node_id: str) -> NodeDir:
    """Node with a summarize_done AND an eval put already enqueued."""
    node = _make_summarized_node(tmp_path, node_id)
    profile_path = tmp_path / "profile_20260505T1200.md"
    profile_path.write_text("Looking for small PME.\n", encoding="utf-8")
    node.append_eval_put(f"summarize/{SUM_FILE}", str(profile_path))
    return node


def test_eval_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["prospect", "eval", "--help"])
    assert result.exit_code == 0
    assert "eval" in result.output


def test_reeval_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["prospect", "reeval", "--help"])
    assert result.exit_code == 0
    assert "reeval" in result.output


def test_eval_no_nodes(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["prospect", "eval"])
    assert result.exit_code == 0
    assert "No nodes found" in result.output


def test_eval_runs_one_step(tmp_path):
    node = _make_eval_ready_node(tmp_path, "acme")
    runner = CliRunner()
    with _agent.override(model=TestModel(custom_output_args={
        "score": "good", "fit": "small team", "dealbreakers": [], "uncertainty": "low",
    })):
        result = runner.invoke(cli, ["prospect", "eval", "-n", "1"])

    assert result.exit_code == 0
    assert "good" in result.output
    assert node.pop_eval_pending() is None


def test_reeval_no_profile(tmp_path):
    _make_eval_ready_node(tmp_path, "acme")
    # Remove the profile
    for f in tmp_path.glob("profile_*.md"):
        f.unlink()
    runner = CliRunner()
    result = runner.invoke(cli, ["prospect", "reeval"])
    assert result.exit_code == 0
    assert "no profile" in result.output.lower()


def test_reeval_enqueues_never_evaled_node(tmp_path):
    """reeval should enqueue a node that was summarized but never evaled."""
    profile_path = tmp_path / "profile_20260505T1200.md"
    profile_path.write_text("Looking for small PME.\n", encoding="utf-8")
    node = _make_summarized_node(tmp_path, "acme")  # no eval queue at all

    runner = CliRunner()
    result = runner.invoke(cli, ["prospect", "reeval"])

    assert result.exit_code == 0
    assert "queued" in result.output
    assert node.pop_eval_pending() is not None


def test_reeval_all_up_to_date(tmp_path):
    from anpe.prospect.eval import EVAL_VERSION
    node = _make_summarized_node(tmp_path, "acme")
    profile_path = tmp_path / "profile_20260505T1200.md"
    profile_path.write_text("Looking for small PME.\n", encoding="utf-8")
    # Mark eval as done with current profile and version
    result_file = node.save_eval_result(
        sum_file=f"summarize/{SUM_FILE}",
        profile_file=str(profile_path),
        eval_version=EVAL_VERSION,
        model="mistral-small-2603",
        score="good", fit="match", dealbreakers=[], uncertainty="low", duration_s=1.0,
    )
    node.mark_eval_done(result_file)

    runner = CliRunner()
    result = runner.invoke(cli, ["prospect", "reeval"])
    assert result.exit_code == 0
    assert "up to date" in result.output
