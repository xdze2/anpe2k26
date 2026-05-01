"""Recherche Entreprises API fetch tool — lookup by SIREN or SIRET number."""

from __future__ import annotations

import json

import httpx

from anpe.enrich.errors import FetchNotFoundError, FetchRetryableError
from anpe.enrich.summarize import EnrichResult, FetchTarget

_SEARCH_URL = "https://recherche-entreprises.api.gouv.fr/search"


def siren_fetch(number: str) -> str:
    """Fetch company data by SIREN (9 digits) or SIRET (14 digits).

    Returns raw JSON as a string. Raises FetchNotFoundError on no results,
    FetchRetryableError on transient network errors.
    """
    number = number.strip().replace(" ", "")
    if len(number) not in (9, 14) or not number.isdigit():
        raise FetchNotFoundError(f"SIREN: {number!r} is not a valid SIREN (9 digits) or SIRET (14 digits)")
    try:
        response = httpx.get(
            _SEARCH_URL,
            params={"q": number, "per_page": 1},
            timeout=10.0,
            headers={"Accept": "application/json"},
        )
    except httpx.TransportError as e:
        raise FetchRetryableError(f"SIREN network error: {e}") from e

    if response.status_code == 429:
        raise FetchRetryableError(f"SIREN rate limit (429) for {number!r}")
    elif response.status_code >= 500:
        raise FetchRetryableError(
            f"SIREN server error {response.status_code} for {number!r}"
        )

    response.raise_for_status()

    data = response.json()
    results = data.get("results", [])
    if not results:
        raise FetchNotFoundError(f"SIREN: no company found for {number!r}")

    result = results[0]
    # The API is a search — verify the returned company actually matches the input number.
    if len(number) == 9 and result.get("siren", "") != number:
        raise FetchNotFoundError(f"SIREN: no company found for SIREN {number!r}")
    if len(number) == 14 and result.get("siege", {}).get("siret", "") != number:
        raise FetchNotFoundError(f"SIREN: no company found for SIRET {number!r}")

    return json.dumps(result)


def siren_process(raw_data: str, previous_summary: str) -> EnrichResult:
    """Format Recherche Entreprises JSON into a structured summary and propose a DDG follow-up."""
    r = json.loads(raw_data)
    siege = r.get("siege", {})

    nom_legal = r.get("nom_complet", "")
    nom_commercial = siege.get("nom_commercial", "") or nom_legal
    siren = r.get("siren", "")
    naf = r.get("activite_principale", "")
    legal_form = r.get("nature_juridique", "")
    size = r.get("tranche_effectif_salarie", "")
    category = r.get("categorie_entreprise", "")
    creation_date = r.get("date_creation", "")
    etat = r.get("etat_administratif", "")
    address = siege.get("geo_adresse", "") or siege.get("adresse", "")

    lines = ["## SIREN data\n"]
    if nom_commercial and nom_commercial != nom_legal:
        lines.append(f"**Name:** {nom_commercial} ({nom_legal})")
    elif nom_legal:
        lines.append(f"**Name:** {nom_legal}")
    if siren:
        lines.append(f"**SIREN:** {siren}")
    if naf:
        lines.append(f"**NAF:** {naf}")
    if legal_form:
        lines.append(f"**Legal form:** {legal_form}")
    if category:
        lines.append(f"**Category:** {category}")
    if size:
        lines.append(f"**Headcount band:** {size}")
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
        new_targets.append(FetchTarget(tool="ddg", target=search_name))

    return EnrichResult(status="ok", summary=summary, new_targets=new_targets)
