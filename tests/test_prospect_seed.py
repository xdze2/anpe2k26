"""Tests for anpe/prospect/seed.py."""

import csv
import pytest
from pathlib import Path

from anpe.prospect.seed import slugify, node_id_for, seed_from_listing


def test_slugify_basic():
    assert slugify("CHAPSVISION") == "chapsvision"


def test_slugify_accents():
    assert slugify("SOCIÉTÉ GÉNÉRALE") == "societe_generale"


def test_slugify_punctuation():
    assert slugify("A & B (France)") == "a_b_france"


def test_node_id_for():
    assert node_id_for("CHAPSVISION", "851035329") == "chapsvision_851035329"


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = ["siret", "siren", "nom_complet", "naf_code", "naf_label",
                  "adresse", "code_postal", "commune", "lat", "lon",
                  "distance_km", "matched_city", "tranche_effectif",
                  "categorie_entreprise", "date_creation"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _make_row(nom: str, siren: str, siret: str = "") -> dict:
    return {"nom_complet": nom, "siren": siren, "siret": siret or siren + "00000"}


def test_seed_creates_nodes(tmp_path, monkeypatch):
    monkeypatch.setattr("anpe.node_dir.NODES_DIR", tmp_path / "nodes")
    monkeypatch.setattr("anpe.prospect.seed.NODES_DIR", tmp_path / "nodes")

    csv_path = tmp_path / "listing.csv"
    _write_csv(csv_path, [
        _make_row("ALPHA", "111111111"),
        _make_row("BETA", "222222222"),
        _make_row("GAMMA", "333333333"),
    ])

    created = seed_from_listing(csv_path, count=2)

    assert created == ["alpha_111111111", "beta_222222222"]
    assert (tmp_path / "nodes" / "alpha_111111111" / "fetch.jsonl").exists()
    assert (tmp_path / "nodes" / "beta_222222222" / "fetch.jsonl").exists()


def test_seed_skips_existing(tmp_path, monkeypatch):
    nodes_dir = tmp_path / "nodes"
    monkeypatch.setattr("anpe.node_dir.NODES_DIR", nodes_dir)
    monkeypatch.setattr("anpe.prospect.seed.NODES_DIR", nodes_dir)

    # Pre-create the first node
    (nodes_dir / "alpha_111111111").mkdir(parents=True)

    csv_path = tmp_path / "listing.csv"
    _write_csv(csv_path, [
        _make_row("ALPHA", "111111111"),
        _make_row("BETA", "222222222"),
        _make_row("GAMMA", "333333333"),
    ])

    created = seed_from_listing(csv_path, count=2)

    assert "alpha_111111111" not in created
    assert created == ["beta_222222222", "gamma_333333333"]


def test_seed_deduplicates_csv(tmp_path, monkeypatch):
    """Same SIREN appearing twice (multi-établissement) counts as one candidate."""
    monkeypatch.setattr("anpe.node_dir.NODES_DIR", tmp_path / "nodes")
    monkeypatch.setattr("anpe.prospect.seed.NODES_DIR", tmp_path / "nodes")

    csv_path = tmp_path / "listing.csv"
    _write_csv(csv_path, [
        _make_row("ALPHA", "111111111", "11111111100001"),
        _make_row("ALPHA", "111111111", "11111111100002"),  # duplicate SIREN
        _make_row("BETA", "222222222"),
    ])

    created = seed_from_listing(csv_path, count=5)

    assert created == ["alpha_111111111", "beta_222222222"]
