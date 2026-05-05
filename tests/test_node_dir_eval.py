"""Tests for NodeDir eval storage methods."""

import json
import pytest
from anpe.node_dir import NodeDir


@pytest.fixture
def node(tmp_path, monkeypatch):
    monkeypatch.setattr("anpe.node_dir.NODES_DIR", tmp_path / "nodes")
    n = NodeDir("test_node")
    n.init()
    return n


def test_pop_eval_pending_none_when_empty(node):
    assert node.pop_eval_pending() is None


def test_append_eval_put_makes_pending(node):
    node.append_eval_put("summarize/sum_foo.json", "../../profile_20260505T1200.md")
    ev = node.pop_eval_pending()
    assert ev is not None
    assert ev["event"] == "put"
    assert ev["sum_file"] == "summarize/sum_foo.json"
    assert ev["profile_file"] == "../../profile_20260505T1200.md"


def test_mark_eval_done_clears_pending(node):
    node.append_eval_put("summarize/sum_foo.json", "../../profile_20260505T1200.md")
    node.mark_eval_done("eval_results/eval_20260505T1201_test_node.json")
    assert node.pop_eval_pending() is None


def test_mark_eval_error_stays_pending(node):
    node.append_eval_put("summarize/sum_foo.json", "../../profile_20260505T1200.md")
    node.mark_eval_error("timeout")
    assert node.pop_eval_pending() is not None


def test_reeval_put_after_done_is_pending(node):
    node.append_eval_put("summarize/sum_foo.json", "../../profile_20260505T1200.md")
    node.mark_eval_done("eval_results/eval_20260505T1201_test_node.json")
    node.append_eval_put("summarize/sum_foo.json", "../../profile_20260506T0900.md")
    ev = node.pop_eval_pending()
    assert ev is not None
    assert ev["profile_file"] == "../../profile_20260506T0900.md"


def test_save_eval_result_writes_file(node):
    filename = node.save_eval_result(
        sum_file="summarize/sum_foo.json",
        profile_file="../../profile_20260505T1200.md",
        eval_version="abc123",
        model="mistral-small-2603",
        score="good",
        fit="small team, clean product",
        dealbreakers=[],
        uncertainty="low",
        duration_s=1.4,
    )
    result_path = node._eval_results_dir / filename
    assert result_path.exists()
    data = json.loads(result_path.read_text())
    assert data["score"] == "good"
    assert data["fit"] == "small team, clean product"
    assert data["eval_version"] == "abc123"


def test_get_latest_eval_result_returns_data(node):
    filename = node.save_eval_result(
        sum_file="summarize/sum_foo.json",
        profile_file="../../profile_20260505T1200.md",
        eval_version="abc123",
        model="mistral-small-2603",
        score="maybe",
        fit="domain unclear",
        dealbreakers=[],
        uncertainty="medium",
        duration_s=2.1,
    )
    node.mark_eval_done(filename)
    result = node.get_latest_eval_result()
    assert result is not None
    assert result["score"] == "maybe"


def test_get_latest_eval_result_none_when_pending(node):
    node.append_eval_put("summarize/sum_foo.json", "../../profile_20260505T1200.md")
    assert node.get_latest_eval_result() is None


def test_is_eval_stale_true_when_no_result(node):
    assert node.is_eval_stale("../../profile_20260505T1200.md", "abc123") is True


def test_is_eval_stale_false_when_current(node):
    filename = node.save_eval_result(
        sum_file="summarize/sum_foo.json",
        profile_file="../../profile_20260505T1200.md",
        eval_version="abc123",
        model="mistral-small-2603",
        score="good",
        fit="match",
        dealbreakers=[],
        uncertainty="low",
        duration_s=1.0,
    )
    node.mark_eval_done(filename)
    assert node.is_eval_stale("../../profile_20260505T1200.md", "abc123") is False


def test_is_eval_stale_true_when_profile_changed(node):
    filename = node.save_eval_result(
        sum_file="summarize/sum_foo.json",
        profile_file="../../profile_20260505T1200.md",
        eval_version="abc123",
        model="mistral-small-2603",
        score="good",
        fit="match",
        dealbreakers=[],
        uncertainty="low",
        duration_s=1.0,
    )
    node.mark_eval_done(filename)
    assert node.is_eval_stale("../../profile_20260506T0900.md", "abc123") is True


def test_is_eval_stale_true_when_version_changed(node):
    filename = node.save_eval_result(
        sum_file="summarize/sum_foo.json",
        profile_file="../../profile_20260505T1200.md",
        eval_version="abc123",
        model="mistral-small-2603",
        score="good",
        fit="match",
        dealbreakers=[],
        uncertainty="low",
        duration_s=1.0,
    )
    node.mark_eval_done(filename)
    assert node.is_eval_stale("../../profile_20260505T1200.md", "newver") is True
