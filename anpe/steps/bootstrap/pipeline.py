"""Bootstrap pipeline: build the company listing from seed_query.yaml.

Steps:
  1. Load seed_query.yaml
  2. For each (departement, naf_code): fetch/cache API results
  3. Extract etablissements from raw results
  4. Filter by distance from each location's lat/lon
  5. Filter by company-level tranche_effectif range
  6. Deduplicate by SIRET
  7. Return rows as a list of dicts (caller writes to vault/CSV)
"""

from __future__ import annotations

import io
import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from anpe.steps.bootstrap.filter import HEADCOUNT_BANDS, tranche_in_range, within_radius
from anpe.steps.bootstrap.search import fetch_pair
from anpe.tools.naf import _load_csv_index as _naf_index

logger = logging.getLogger(__name__)

_OUTPUT_COLUMNS = [
    "siret", "siren", "nom_complet", "naf_code", "naf_label",
    "adresse", "code_postal", "commune",
    "lat", "lon", "distance_km", "matched_city",
    "tranche_effectif", "categorie_entreprise", "date_creation",
]


@dataclass
class LocationConfig:
    city: str
    lat: float
    lon: float
    radius_km: float
    departements: list[str]


@dataclass
class UserProfile:
    naf_codes: list[str]
    locations: list[LocationConfig]
    tranche_min: str
    tranche_max: str
    etat_administratif: str = "A"


def load_profile(profile_path: Path) -> UserProfile:
    raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    locations = [
        LocationConfig(
            city=loc["city"],
            lat=float(loc["lat"]),
            lon=float(loc["lon"]),
            radius_km=float(loc["radius_km"]),
            departements=[str(d) for d in loc["departements"]],
        )
        for loc in raw["locations"]
    ]
    size = raw.get("size", {})
    return UserProfile(
        naf_codes=raw["naf_codes"],
        locations=locations,
        tranche_min=str(size.get("tranche_min", "00")),
        tranche_max=str(size.get("tranche_max", "53")),
        etat_administratif=raw.get("etat_administratif", "A"),
    )


def _extract_etablissements(result: dict) -> list[dict]:
    """Pull établissements out of one API result object."""
    matching = result.get("matching_etablissements") or []
    if matching:
        return matching
    siege = result.get("siege")
    return [siege] if siege else []


def _row_from_etab(
    etab: dict,
    result: dict,
    distance_km: float,
    matched_city: str,
) -> dict[str, Any]:
    naf_code = result.get("activite_principale", "")
    naf_label = _naf_index().get(naf_code, "")
    tranche = result.get("tranche_effectif_salarie", "")
    return {
        "siret": etab.get("siret", ""),
        "siren": result.get("siren", ""),
        "nom_complet": result.get("nom_complet", ""),
        "naf_code": naf_code,
        "naf_label": naf_label,
        "adresse": etab.get("geo_adresse", "") or etab.get("adresse", ""),
        "code_postal": etab.get("code_postal", ""),
        "commune": etab.get("libelle_commune", ""),
        "lat": etab.get("latitude", ""),
        "lon": etab.get("longitude", ""),
        "distance_km": round(distance_km, 2),
        "matched_city": matched_city,
        "tranche_effectif": HEADCOUNT_BANDS.get(tranche, tranche),
        "categorie_entreprise": result.get("categorie_entreprise", ""),
        "date_creation": result.get("date_creation", ""),
    }


def run(profile_path: Path, refresh: bool = False) -> list[dict[str, Any]]:
    """Run the full bootstrap pipeline. Returns rows as a list of dicts."""
    profile = load_profile(profile_path)

    pairs: list[tuple[str, str]] = [
        (dep, naf)
        for loc in profile.locations
        for dep in loc.departements
        for naf in profile.naf_codes
    ]

    all_results: list[dict] = []  # type: ignore[type-arg]
    for dep, naf in pairs:
        results = fetch_pair(dep, naf, profile.etat_administratif, refresh)
        all_results.extend(results)

    logger.info("Total raw results across all pairs: %d", len(all_results))

    rows: list[dict[str, Any]] = []
    seen_sirets: set[str] = set()

    for result in all_results:
        tranche = result.get("tranche_effectif_salarie", "")
        if not tranche_in_range(tranche, profile.tranche_min, profile.tranche_max):
            continue

        for etab in _extract_etablissements(result):
            siret = etab.get("siret", "")
            if not siret or siret in seen_sirets:
                continue

            try:
                etab_lat = float(etab["latitude"])
                etab_lon = float(etab["longitude"])
            except (KeyError, TypeError, ValueError):
                continue

            for loc in profile.locations:
                d = within_radius(etab_lat, etab_lon, loc.lat, loc.lon, loc.radius_km)
                if d is not None:
                    seen_sirets.add(siret)
                    rows.append(_row_from_etab(etab, result, d, loc.city))
                    break

    logger.info("Found %d companies", len(rows))
    return rows


def rows_to_jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Serialize rows to JSONL bytes (UTF-8), one JSON object per line."""
    import json
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def rows_to_csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Serialize rows to CSV bytes (UTF-8)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_OUTPUT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")
