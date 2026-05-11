from __future__ import annotations

import json
from pathlib import Path

import pytest

from anpe.engine.vault import Vault
from anpe.steps.fetch_ddg_step import FetchDdgStep, _ddg_target


def _make_vault(tmp_path: Path) -> Vault:
    return Vault(root=tmp_path / "vault")


_SIREN_RAW = {
    "nom_complet": "Acme Corp",
    "siren": "123456789",
    "siege": {"nom_commercial": "Acme"},
    "section_activite_principale": "J",
}

_SIREN_RAW_NON_J = {
    "nom_complet": "Beta SA",
    "siren": "987654321",
    "siege": {},
    "section_activite_principale": "C",
}


def _write_siren_output(vault: Vault, node_id: str, siren_raw: dict) -> None:
    uri = vault.output_uri(node_id, "fetch_siren")
    path = vault.root / uri
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(siren_raw))


def test_scan_yields_nothing_when_nodes_missing(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    assert list(FetchDdgStep().scan(vault)) == []


def test_scan_yields_candidate_for_each_siren_output(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_siren_output(vault, "acme_corp_123456789", _SIREN_RAW)
    _write_siren_output(vault, "beta_sa_987654321", _SIREN_RAW_NON_J)
    candidates = list(FetchDdgStep().scan(vault))
    assert len(candidates) == 2
    assert all(not c.skip for c in candidates)


def test_scan_marks_skip_when_ddg_output_exists(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_123456789"
    _write_siren_output(vault, node_id, _SIREN_RAW)

    step = FetchDdgStep()
    ddg_uri = vault.output_uri(node_id, step.name)
    (vault.root / ddg_uri).parent.mkdir(parents=True, exist_ok=True)
    (vault.root / ddg_uri).write_text("[]")

    candidates = list(step.scan(vault))
    assert len(candidates) == 1
    assert candidates[0].skip is True


def test_scan_overwrite_yields_done_nodes(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    node_id = "acme_corp_123456789"
    _write_siren_output(vault, node_id, _SIREN_RAW)

    step = FetchDdgStep()
    ddg_uri = vault.output_uri(node_id, step.name)
    (vault.root / ddg_uri).parent.mkdir(parents=True, exist_ok=True)
    (vault.root / ddg_uri).write_text("[]")

    candidates = list(step.scan(vault, overwrite=True))
    assert len(candidates) == 1
    assert candidates[0].skip is False


def test_scan_passes_correct_target(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_siren_output(vault, "acme_corp_123456789", _SIREN_RAW)
    candidates = list(FetchDdgStep().scan(vault))
    assert candidates[0].args["target"] == "Acme entreprise informatique"


def test_ddg_target_naf_j() -> None:
    raw = {
        "nom_complet": "Foo",
        "siege": {"nom_commercial": "Foo Tech"},
        "section_activite_principale": "J",
    }
    assert _ddg_target(raw) == "Foo Tech entreprise informatique"


def test_ddg_target_non_j() -> None:
    raw = {"nom_complet": "Bar SA", "siege": {}, "section_activite_principale": "C"}
    assert _ddg_target(raw) == "Bar SA entreprise"


def test_work_writes_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _make_vault(tmp_path)
    vault.root.mkdir(parents=True)

    monkeypatch.setattr(
        "anpe.clients.ddg.DdgClient.__call__",
        lambda self, query, **kw: '[{"title": "t", "href": "http://x.com", "body": "b"}]',
    )

    logs: list[str] = []
    step = FetchDdgStep()
    node_id = "acme_corp_123456789"
    siren_uri = vault.output_uri(node_id, "fetch_siren")
    args = {"node_id": node_id, "target": "Acme entreprise", "siren_uri": siren_uri}
    step.work(args, vault, logs.append)

    uri = vault.output_uri(node_id, step.name)
    assert vault.exists(uri)
    assert "title" in (vault.root / uri).read_text()
