"""Recherche Entreprises API fetch tool — lookup by SIREN or SIRET number."""

from __future__ import annotations

import json

from anpe.clients.siren import siren_fetch
from anpe.enrich.summarize import EnrichResult, FetchTarget
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
    """Format Recherche Entreprises JSON into a structured summary and propose a DDG follow-up."""
    r = json.loads(raw_data)
    siege = r.get("siege", {})

    nom_legal = r.get("nom_complet", "")
    nom_commercial = siege.get("nom_commercial", "") or nom_legal
    siren = r.get("siren", "")
    naf_code = r.get("activite_principale", "")
    naf_label = _naf_index().get(naf_code, "")
    naf = f"{naf_code} — {naf_label}" if naf_label else naf_code
    category = r.get("categorie_entreprise", "")
    size_code = r.get("tranche_effectif_salarie", "")
    size = _HEADCOUNT_BANDS.get(size_code, size_code) if size_code else ""
    creation_date = r.get("date_creation", "")
    etat = r.get("etat_administratif", "")
    address = siege.get("geo_adresse", "") or siege.get("adresse", "")

    dirigeants = r.get("dirigeants", [])
    ceo = next(
        (f"{d.get('prenoms', '')} {d.get('nom', '')}".strip()
         for d in dirigeants
         if d.get("type_dirigeant") == "personne physique"
         and "directeur" in d.get("qualite", "").lower()),
        None,
    )

    finances = r.get("finances", {})
    latest_year = max(finances.keys(), default=None) if finances else None
    revenue = finances[latest_year].get("ca") if latest_year else None
    net_result = finances[latest_year].get("resultat_net") if latest_year else None

    lines = ["## SIREN data\n"]
    if nom_commercial and nom_commercial != nom_legal:
        lines.append(f"**Name:** {nom_commercial} ({nom_legal})")
    elif nom_legal:
        lines.append(f"**Name:** {nom_legal}")
    if siren:
        lines.append(f"**SIREN:** {siren}")
    if naf:
        lines.append(f"**NAF:** {naf}")
    if category:
        lines.append(f"**Category:** {category}")
    if size:
        lines.append(f"**Headcount:** {size} employees")
    if revenue is not None:
        lines.append(f"**Revenue ({latest_year}):** {revenue / 1_000_000:.1f}M€")
    if net_result is not None:
        lines.append(f"**Net result ({latest_year}):** {net_result / 1_000_000:.2f}M€")
    if ceo:
        lines.append(f"**CEO:** {ceo}")
    if creation_date:
        lines.append(f"**Created:** {creation_date}")
    if etat:
        lines.append(f"**Status:** {etat}")
    if address:
        lines.append(f"**Address:** {address}")

    summary = "\n".join(lines)
    if previous_summary:
        summary = previous_summary + "\n\n" + summary

    search_name = nom_commercial or nom_legal
    new_targets: list[FetchTarget] = []
    if search_name:
        naf_section = r.get("section_activite_principale", "")
        # Add sector context to avoid ambiguous queries (e.g. "SMILE" → dictionary results)
        suffix = " entreprise informatique" if naf_section == "J" else " entreprise"
        new_targets.append(FetchTarget(tool="ddg", target=search_name + suffix))

    return EnrichResult(status="ok", summary=summary, new_targets=new_targets)
