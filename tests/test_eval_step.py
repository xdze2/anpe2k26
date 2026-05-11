from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anpe.engine.vault import Vault
from anpe.steps.eval_step import EvalStep
from anpe.steps.eval_fn import EvalResult


def _make_vault(tmp_path: Path) -> Vault:
    return Vault(root=tmp_path / "vault")


def _write(vault: Vault, uri: str, content: str) -> None:
    path = vault.root / uri
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


_SUMMARY_OK = json.dumps({"status": "ok", "summary": "A small SaaS company."})
_SUMMARY_NOT_RELEVANT = json.dumps({"status": "not_relevant", "summary": ""})
_PROFILE = "Looking for small PME, no ESN."


def test_scan_yields_nothing_when_no_nodes(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write(vault, "user_preference.md", _PROFILE)
    assert list(EvalStep().scan(vault)) == []


def test_scan_yields_nothing_when_no_profile(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_12345678"
    _write(vault, vault.output_uri(node_id, "summarize_ddg"), _SUMMARY_OK)
    assert list(EvalStep().scan(vault)) == []


def test_scan_yields_candidate_for_summarized_node(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_12345678"
    _write(vault, vault.output_uri(node_id, "summarize_ddg"), _SUMMARY_OK)
    _write(vault, "user_preference.md", _PROFILE)
    candidates = list(EvalStep().scan(vault))
    assert len(candidates) == 1
    assert not candidates[0].skip


def test_scan_marks_skip_when_eval_exists(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_12345678"
    step = EvalStep()
    _write(vault, vault.output_uri(node_id, "summarize_ddg"), _SUMMARY_OK)
    _write(vault, vault.output_uri(node_id, step.name), "{}")
    _write(vault, "user_preference.md", _PROFILE)
    candidates = list(step.scan(vault))
    assert len(candidates) == 1
    assert candidates[0].skip is True


def test_scan_overwrite_yields_done_nodes(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_12345678"
    step = EvalStep()
    _write(vault, vault.output_uri(node_id, "summarize_ddg"), _SUMMARY_OK)
    _write(vault, vault.output_uri(node_id, step.name), "{}")
    _write(vault, "user_preference.md", _PROFILE)
    candidates = list(step.scan(vault, overwrite=True))
    assert len(candidates) == 1
    assert candidates[0].skip is False


def test_scan_skips_non_relevant_by_default(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_ok = "acme_corp_12345678"
    node_nr = "esn_corp_87654321"
    _write(vault, vault.output_uri(node_ok, "summarize_ddg"), _SUMMARY_OK)
    _write(vault, vault.output_uri(node_nr, "summarize_ddg"), _SUMMARY_NOT_RELEVANT)
    _write(vault, "user_preference.md", _PROFILE)

    candidates = list(EvalStep().scan(vault))
    by_node = {c.node_id: c for c in candidates}
    assert node_ok in by_node and not by_node[node_ok].skip
    assert node_nr in by_node and by_node[node_nr].skip is True


def test_scan_keep_non_relevant_includes_not_relevant(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_nr = "esn_corp_87654321"
    _write(vault, vault.output_uri(node_nr, "summarize_ddg"), _SUMMARY_NOT_RELEVANT)
    _write(vault, "user_preference.md", _PROFILE)

    candidates = list(EvalStep().scan(vault, keep_non_relevant=True))
    assert len(candidates) == 1
    assert candidates[0].skip is False


def test_work_writes_eval_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_12345678"
    _write(vault, vault.output_uri(node_id, "summarize_ddg"), _SUMMARY_OK)
    _write(vault, "user_preference.md", _PROFILE)

    fake_result = EvalResult(
        score="good",
        fit="small team, clean product",
        dealbreakers=[],
        uncertainty="low",
        prompt="...",
    )
    monkeypatch.setattr("anpe.steps.eval_step.llm_eval", MagicMock(return_value=fake_result))

    step = EvalStep()
    summary_uri = vault.output_uri(node_id, "summarize_ddg")
    args = {"node_id": node_id, "summary_uri": summary_uri, "profile_uri": "user_preference.md"}
    step.work(args, vault, lambda _: None)

    eval_uri = vault.output_uri(node_id, step.name)
    assert vault.exists(eval_uri)
    saved = json.loads((vault.root / eval_uri).read_text())
    assert saved["score"] == "good"
    assert "fit" in saved
    assert "dealbreakers" in saved
