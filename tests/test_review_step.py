from __future__ import annotations

import json
from pathlib import Path

from anpe.engine.vault import Vault
from anpe.steps.review_step import ReviewStep


def _make_vault(tmp_path: Path) -> Vault:
    return Vault(root=tmp_path / "vault")


def _write(vault: Vault, uri: str, content: str) -> None:
    path = vault.root / uri
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


_SUMMARY_OK = json.dumps({"status": "ok", "summary": "A small SaaS company."})
_SUMMARY_NOT_RELEVANT = json.dumps({"status": "not_relevant", "summary": ""})


def test_scan_yields_nothing_when_no_nodes(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    assert list(ReviewStep().scan(vault)) == []


def test_scan_yields_candidate_for_summarized_node(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_12345678"
    _write(vault, vault.output_uri(node_id, "summarize_ddg"), _SUMMARY_OK)
    candidates = list(ReviewStep().scan(vault))
    assert len(candidates) == 1
    assert not candidates[0].skip
    assert candidates[0].node_id == node_id


def test_scan_marks_skip_when_review_exists(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_12345678"
    step = ReviewStep()
    _write(vault, vault.output_uri(node_id, "summarize_ddg"), _SUMMARY_OK)
    _write(vault, vault.output_uri(node_id, step.name), "{}")
    candidates = list(step.scan(vault))
    assert len(candidates) == 1
    assert candidates[0].skip is True


def test_scan_overwrite_marks_skip_false(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_12345678"
    step = ReviewStep()
    _write(vault, vault.output_uri(node_id, "summarize_ddg"), _SUMMARY_OK)
    _write(vault, vault.output_uri(node_id, step.name), "{}")
    candidates = list(step.scan(vault, overwrite=True))
    assert len(candidates) == 1
    assert candidates[0].skip is False


def test_scan_excludes_non_ok_statuses(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_ok = "acme_corp_12345678"
    node_nr = "esn_corp_87654321"
    _write(vault, vault.output_uri(node_ok, "summarize_ddg"), _SUMMARY_OK)
    _write(vault, vault.output_uri(node_nr, "summarize_ddg"), _SUMMARY_NOT_RELEVANT)
    candidates = list(ReviewStep().scan(vault))
    node_ids = [c.node_id for c in candidates]
    assert node_ok in node_ids
    assert node_nr not in node_ids


def test_scan_includes_siren_and_eval_uris_when_present(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_12345678"
    _write(vault, vault.output_uri(node_id, "summarize_ddg"), _SUMMARY_OK)
    _write(vault, vault.output_uri(node_id, "fetch_siren"), "{}")
    _write(vault, vault.output_uri(node_id, "eval"), "{}")
    candidates = list(ReviewStep().scan(vault))
    assert len(candidates) == 1
    args = candidates[0].args
    assert args["siren_uri"] is not None
    assert args["eval_uri"] is not None
