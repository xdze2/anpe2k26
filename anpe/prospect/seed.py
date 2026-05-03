"""Seed prospect nodes from the company listing CSV."""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

from anpe.node_dir import NODES_DIR, NodeDir


def slugify(text: str) -> str:
    """Lowercase, strip accents, replace non-alphanumeric runs with '_'."""
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    return slug


def node_id_for(nom_complet: str, siren: str) -> str:
    return f"{slugify(nom_complet)}_{siren}"


def seed_from_listing(csv_path: Path, count: int) -> list[str]:
    """Read CSV, deduplicate by node_id, skip existing nodes, create up to `count` new ones.

    Returns the list of created node_ids.
    """
    rows = _read_unique_rows(csv_path)

    candidates = [r for r in rows if not NodeDir(r["node_id"]).exists()]

    to_create = candidates[:count]

    created = []
    for row in to_create:
        node = NodeDir(row["node_id"])
        node.init()
        node.set_frontmatter({"siren": row["siren"], "name": row["nom_complet"]})
        node.append_target("siren", row["siren"])
        created.append(row["node_id"])

    return created


def _read_unique_rows(csv_path: Path) -> list[dict[str, str]]:
    """Read CSV and deduplicate by node_id, keeping first occurrence."""
    seen: set[str] = set()
    rows = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        for record in csv.DictReader(f):
            nid = node_id_for(record["nom_complet"], record["siren"])
            if nid not in seen:
                seen.add(nid)
                rows.append({"node_id": nid, "nom_complet": record["nom_complet"], "siren": record["siren"]})
    return rows
