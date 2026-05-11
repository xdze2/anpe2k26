from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from anpe.engine.vault import Vault
from anpe.steps.summarize_ddg_step import SummarizeDdgStep
from anpe.steps.types import SummarizeResult


def _make_vault(tmp_path: Path) -> Vault:
    return Vault(root=tmp_path / "vault")


_SIREN_RAW = {
    "nom_complet": "Acme Corp",
    "siren": "123456789",
    "siege": {"nom_commercial": "Acme"},
    "activite_principale": "62.01Z",
    "section_activite_principale": "J",
}

_DDG_RAW = json.dumps([{"title": "Acme", "href": "https://acme.fr", "body": "Software company"}])


def _write_file(vault: Vault, uri: str, content: str) -> None:
    path = vault.root / uri
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_scan_yields_nothing_when_nodes_missing(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    assert list(SummarizeDdgStep().scan(vault)) == []


def test_scan_yields_candidate_for_each_ddg_output(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_123456789"
    _write_file(vault, vault.output_uri(node_id, "fetch_ddg"), _DDG_RAW)
    candidates = list(SummarizeDdgStep().scan(vault))
    assert len(candidates) == 1
    assert not candidates[0].skip


def test_scan_marks_skip_when_summary_exists(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_123456789"
    step = SummarizeDdgStep()
    _write_file(vault, vault.output_uri(node_id, "fetch_ddg"), _DDG_RAW)
    _write_file(vault, vault.output_uri(node_id, step.name), "{}")
    candidates = list(step.scan(vault))
    assert len(candidates) == 1
    assert candidates[0].skip is True


def test_scan_overwrite_yields_done_nodes(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_123456789"
    step = SummarizeDdgStep()
    _write_file(vault, vault.output_uri(node_id, "fetch_ddg"), _DDG_RAW)
    _write_file(vault, vault.output_uri(node_id, step.name), "{}")
    candidates = list(step.scan(vault, overwrite=True))
    assert len(candidates) == 1
    assert candidates[0].skip is False


def test_work_writes_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_123456789"
    _write_file(vault, vault.output_uri(node_id, "fetch_siren"), json.dumps(_SIREN_RAW))
    _write_file(vault, vault.output_uri(node_id, "fetch_ddg"), _DDG_RAW)

    fake_result = SummarizeResult(
        status="ok",
        summary="A software company.",
        new_targets=[],
        model="mistral-small-2603",
        version="abc123",
        prompt="...",
    )

    monkeypatch.setattr(
        "anpe.steps.summarize_ddg_step.ddg_summarize",
        AsyncMock(return_value=fake_result),
    )

    logs: list[str] = []
    step = SummarizeDdgStep()
    ddg_uri = vault.output_uri(node_id, "fetch_ddg")
    siren_uri = vault.output_uri(node_id, "fetch_siren")
    step.work({"node_id": node_id, "ddg_uri": ddg_uri, "siren_uri": siren_uri}, vault, logs.append)

    uri = vault.output_uri(node_id, step.name)
    assert vault.exists(uri)
    saved = json.loads((vault.root / uri).read_text())
    assert saved["status"] == "ok"
    assert "summary" in saved


def test_work_raises_fatal_when_siren_missing(tmp_path: Path) -> None:
    from anpe.engine.types import FatalError

    vault = _make_vault(tmp_path)
    node_id = "acme_corp_123456789"
    _write_file(vault, vault.output_uri(node_id, "fetch_ddg"), _DDG_RAW)

    step = SummarizeDdgStep()
    ddg_uri = vault.output_uri(node_id, "fetch_ddg")
    siren_uri = vault.output_uri(node_id, "fetch_siren")
    with pytest.raises(FatalError):
        args = {"node_id": node_id, "ddg_uri": ddg_uri, "siren_uri": siren_uri}
        step.work(args, vault, lambda _: None)
