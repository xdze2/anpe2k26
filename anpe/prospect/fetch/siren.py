"""Recherche Entreprises API fetch tool — lookup by SIREN or SIRET number."""

from __future__ import annotations

import json

from anpe.clients.siren import siren_fetch
from anpe.prospect.types import FetchTarget, SummarizeResult

__all__ = ["siren_fetch", "siren_summarize", "SIREN_SUMMARIZE_VERSION"]

SIREN_SUMMARIZE_VERSION = "v3"


async def siren_summarize(raw_data: str, previous_summary: str, company_profile: str = "") -> SummarizeResult:
    """Propose a DDG follow-up search based on SIREN registry data."""
    r = json.loads(raw_data)
    siege = r.get("siege", {})

    nom_legal = r.get("nom_complet", "")
    nom_commercial = siege.get("nom_commercial", "") or nom_legal

    new_targets: list[FetchTarget] = []
    search_name = nom_commercial or nom_legal
    if search_name:
        naf_section = r.get("section_activite_principale", "")
        suffix = " entreprise informatique" if naf_section == "J" else " entreprise"
        new_targets.append(FetchTarget(tool="ddg", target=search_name + suffix))

    return SummarizeResult(
        status="ok",
        summary=previous_summary,
        new_targets=new_targets,
        version=SIREN_SUMMARIZE_VERSION,
        model="siren_api",
    )
