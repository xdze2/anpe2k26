from __future__ import annotations

from pathlib import Path

import pytest

from anpe.engine.vault import Vault
from anpe.steps.bootstrap_step import BootstrapStep, _OUTPUT_URI, _SEED_URI


def _make_vault(tmp_path: Path) -> Vault:
    return Vault(root=tmp_path / "vault")


def test_scan_yields_nothing_when_seed_missing(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    step = BootstrapStep()
    assert list(step.scan(vault)) == []


def test_scan_yields_candidate_when_seed_exists_no_output(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    vault.root.mkdir(parents=True)
    (vault.root / _SEED_URI).write_text("query: test")
    step = BootstrapStep()
    candidates = list(step.scan(vault))
    assert len(candidates) == 1
    assert candidates[0].node_id is None


def test_scan_yields_skipped_when_output_exists_no_overwrite(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    vault.root.mkdir(parents=True)
    (vault.root / _SEED_URI).write_text("query: test")
    (vault.root / _OUTPUT_URI).write_text("{}")
    step = BootstrapStep()
    candidates = list(step.scan(vault))
    assert len(candidates) == 1
    assert candidates[0].skip is True


def test_scan_yields_candidate_when_overwrite_true(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    vault.root.mkdir(parents=True)
    (vault.root / _SEED_URI).write_text("query: test")
    (vault.root / _OUTPUT_URI).write_text("{}")
    step = BootstrapStep()
    candidates = list(step.scan(vault, overwrite=True))
    assert len(candidates) == 1


def test_work_writes_listing_jsonl(tmp_path: Path, monkeypatch) -> None:
    vault = _make_vault(tmp_path)
    vault.root.mkdir(parents=True)
    (vault.root / _SEED_URI).write_text("query: test")

    fake_rows = [{"siret": "12345", "name": "Acme"}]

    import anpe.steps.bootstrap_step as mod
    monkeypatch.setattr(mod, "_pipeline_run", lambda path: fake_rows)

    logs: list[str] = []
    step = BootstrapStep()
    step.work({"seed_uri": _SEED_URI}, vault, logs.append)

    out_path = vault.root / _OUTPUT_URI
    assert out_path.exists()
    content = out_path.read_text()
    assert "12345" in content
    assert any("1 rows" in msg for msg in logs)
