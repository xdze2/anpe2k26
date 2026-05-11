from __future__ import annotations

import json
from pathlib import Path

import pytest

from anpe.engine.vault import Vault
from anpe.steps.fetch_siren_step import FetchSirenStep, _LISTING_URI
from anpe.steps.seed_fn import node_id_for


def _make_vault(tmp_path: Path) -> Vault:
    return Vault(root=tmp_path / "vault")


def _write_listing(vault: Vault, rows: list[dict]) -> None:  # type: ignore[type-arg]
    vault.root.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(json.dumps(r) for r in rows)
    (vault.root / _LISTING_URI).write_text(lines)


_ROW = {"nom_complet": "Acme Corp", "siren": "123456789"}


def test_scan_yields_nothing_when_listing_missing(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    assert list(FetchSirenStep().scan(vault)) == []


def test_scan_yields_candidate_for_each_row(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_listing(vault, [_ROW, {"nom_complet": "Beta SA", "siren": "987654321"}])
    candidates = list(FetchSirenStep().scan(vault))
    assert len(candidates) == 2
    assert all(not c.skip for c in candidates)


def _write_output(vault: Vault, step: FetchSirenStep, row: dict) -> None:
    node_id = node_id_for(row["nom_complet"], row["siren"])
    uri = vault.output_uri(node_id, step.name)
    (vault.root / uri).parent.mkdir(parents=True, exist_ok=True)
    (vault.root / uri).write_text("{}")


def test_scan_marks_skip_when_output_exists(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_listing(vault, [_ROW])
    step = FetchSirenStep()
    _write_output(vault, step, _ROW)
    candidates = list(step.scan(vault))
    assert len(candidates) == 1
    assert candidates[0].skip is True


def test_scan_overwrite_yields_done_nodes(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    _write_listing(vault, [_ROW])
    step = FetchSirenStep()
    _write_output(vault, step, _ROW)
    candidates = list(step.scan(vault, overwrite=True))
    assert len(candidates) == 1


def test_work_writes_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _make_vault(tmp_path)
    vault.root.mkdir(parents=True)

    monkeypatch.setattr("anpe.clients.siren.SirenClient.__call__", lambda self, siren: '{"siren": "' + siren + '"}')

    logs: list[str] = []
    step = FetchSirenStep()
    node_id = "abc123def456"
    step.work({"node_id": node_id, "siren": "123456789"}, vault, logs.append)

    uri = vault.output_uri(node_id, step.name)
    assert vault.exists(uri)
    assert "123456789" in (vault.root / uri).read_text()
