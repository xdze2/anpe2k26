"""Recherche Entreprises API fetch tool — lookup by SIREN or SIRET number."""

from __future__ import annotations

import json

from anpe.clients.siren import siren_fetch
from anpe.prospect.summarize import EnrichResult, FetchTarget
from anpe.tools.naf import _load_csv_index as _naf_index

__all__ = ["siren_fetch", "siren_process"]


_HEADCOUNT_BANDS: dict[str, str] = {
    "00": "0", "01": "1-2", "02": "3-5", "03": "6-9",
    "11": "10-19", "12": "20-49", "21": "50-99",
    "22": "100-199", "31": "200-249", "32": "250-499",
    "41": "500-999", "42": "1 000-1 999", "51": "2 000-4 999",
    "52": "5 000-9 999", "53": "10 000+",
}


async def siren_process(raw_data: str, previous_summary: str) -> EnrichResult:
    """Extract registry fields into frontmatter and propose a DDG follow-up."""
    r = json.loads(raw_data)
    siege = r.get("siege", {})

    nom_legal = r.get("nom_complet", "")
    nom_commercial = siege.get("nom_commercial", "") or nom_legal
    siren = r.get("siren", "")
    naf_code = r.get("activite_principale", "")
    naf_label = _naf_index().get(naf_code, "")
    category = r.get("categorie_entreprise", "")
    size_code = r.get("tranche_effectif_salarie", "")
    city = siege.get("libelle_commune", "") or siege.get("commune", "")

    fm: dict = {}  # type: ignore[type-arg]
    if siren:
        fm["siren"] = siren
    if nom_commercial:
        fm["name"] = nom_commercial
    if nom_commercial != nom_legal and nom_legal:
        fm["name_legal"] = nom_legal
    if naf_code:
        fm["naf"] = f"{naf_code} — {naf_label}" if naf_label else naf_code
    if category:
        fm["category"] = category
    if size_code:
        fm["headcount"] = _HEADCOUNT_BANDS.get(size_code, size_code)
    if city:
        fm["city"] = city

    search_name = nom_commercial or nom_legal
    new_targets: list[FetchTarget] = []
    if search_name:
        naf_section = r.get("section_activite_principale", "")
        suffix = " entreprise informatique" if naf_section == "J" else " entreprise"
        new_targets.append(FetchTarget(tool="ddg", target=search_name + suffix))

    return EnrichResult(
        status="ok",
        summary=previous_summary,
        new_targets=new_targets,
        frontmatter=fm,
    )
