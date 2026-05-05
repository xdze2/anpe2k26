"""Test that enrich_step appends an eval put after a successful summarize."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock

import anpe.profile as profile_mod
from anpe.node_dir import NodeDir
from anpe.prospect.types import SummarizeResult, FetchTarget
from anpe.prospect.pipeline import enrich_step


@pytest.fixture(autouse=True)
def patch_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr("anpe.node_dir.NODES_DIR", tmp_path / "nodes")
    monkeypatch.setattr(profile_mod, "_USER_DATA_DIR", tmp_path)


def _make_node_with_ddg(tmp_path: Path, node_id: str) -> NodeDir:
    node = NodeDir(node_id)
    node.init()
    # Write fake DDG raw data (valid JSON array)
    raw = json.dumps([{"title": "Acme", "href": "https://acme.fr", "body": "A great PME."}])
    (node._raw_dir / "raw_ddg_acme_20260505T120000.json").write_text(raw, encoding="utf-8")
    node.append_target("ddg", "Acme France")
    return node


@pytest.mark.asyncio
async def test_enrich_step_appends_eval_put_on_ok(tmp_path):
    profile_path = tmp_path / "profile_20260505T1200.md"
    profile_path.write_text("Looking for small PME.\n", encoding="utf-8")

    node = _make_node_with_ddg(tmp_path, "acme")

    ok_result = SummarizeResult(
        status="ok",
        summary="A 20-person SaaS in Toulouse.",
        new_targets=[],
    )

    with patch("anpe.prospect.pipeline.FETCH_TOOLS") as mock_tools:
        mock_tool = mock_tools.__getitem__.return_value
        mock_tool.raw_ext = "json"
        mock_tool.summarize = AsyncMock(return_value=ok_result)
        mock_tool.fetch = lambda t: json.dumps([{"title": "t", "href": "https://x.fr", "body": "b"}])
        mock_tools.get.return_value = mock_tool
        mock_tools.__contains__ = lambda self, k: True

        log = await enrich_step("acme")

    assert log.status == "ok"

    last_eval = node._last_eval_event()
    assert last_eval is not None
    assert last_eval["event"] == "put"
    assert "sum_file" in last_eval
    assert last_eval["profile_file"] == str(profile_path)


@pytest.mark.asyncio
async def test_enrich_step_no_eval_put_on_not_relevant(tmp_path):
    profile_path = tmp_path / "profile_20260505T1200.md"
    profile_path.write_text("Looking for small PME.\n", encoding="utf-8")

    node = _make_node_with_ddg(tmp_path, "irrelevant")

    not_relevant_result = SummarizeResult(
        status="not_relevant",
        summary="",
        new_targets=[],
    )

    with patch("anpe.prospect.pipeline.FETCH_TOOLS") as mock_tools:
        mock_tool = mock_tools.__getitem__.return_value
        mock_tool.raw_ext = "json"
        mock_tool.summarize = AsyncMock(return_value=not_relevant_result)
        mock_tool.fetch = lambda t: json.dumps([{"title": "t", "href": "https://x.fr", "body": "b"}])
        mock_tools.get.return_value = mock_tool
        mock_tools.__contains__ = lambda self, k: True

        log = await enrich_step("irrelevant")

    assert log.status == "not_relevant"
    assert node._last_eval_event() is None


@pytest.mark.asyncio
async def test_enrich_step_no_eval_put_without_profile(tmp_path):
    # No profile file — active_profile_file() returns None
    node = _make_node_with_ddg(tmp_path, "noprofile")

    ok_result = SummarizeResult(status="ok", summary="Good company.", new_targets=[])

    with patch("anpe.prospect.pipeline.FETCH_TOOLS") as mock_tools:
        mock_tool = mock_tools.__getitem__.return_value
        mock_tool.raw_ext = "json"
        mock_tool.summarize = AsyncMock(return_value=ok_result)
        mock_tool.fetch = lambda t: json.dumps([{"title": "t", "href": "https://x.fr", "body": "b"}])
        mock_tools.get.return_value = mock_tool
        mock_tools.__contains__ = lambda self, k: True

        log = await enrich_step("noprofile")

    assert log.status == "ok"
    assert node._last_eval_event() is None
