"""Compile a human-readable markdown snapshot of a node from vault artifacts."""

from __future__ import annotations

import json

from anpe.engine.vault import Vault

_HEADCOUNT_BANDS: dict[str, str] = {
    "00": "0", "01": "1-2", "02": "3-5", "03": "6-9",
    "11": "10-19", "12": "20-49", "21": "50-99",
    "22": "100-199", "31": "200-249", "32": "250-499",
    "41": "500-999", "42": "1 000-1 999", "51": "2 000-4 999",
    "52": "5 000-9 999", "53": "10 000+",
}

_SCORE_LABEL = {
    "good": "✓ good",
    "maybe": "? maybe",
    "discard": "✗ discard",
    "enrich": "↑ enrich",
}


def _siren_section(raw_json: str) -> str:
    raw = json.loads(raw_json)
    siege = raw.get("siege", {})

    nom_legal = raw.get("nom_complet", "")
    nom_commercial = siege.get("nom_commercial", "") or nom_legal
    siren = raw.get("siren", "")
    naf = raw.get("activite_principale", "")
    size_code = raw.get("tranche_effectif_salarie", "")
    headcount = _HEADCOUNT_BANDS.get(size_code, size_code) if size_code else ""
    category = raw.get("categorie_entreprise", "")
    city = siege.get("libelle_commune", "") or siege.get("commune", "")

    lines = [f"## {nom_commercial}"]
    meta_parts = []
    if siren:
        meta_parts.append(f"SIREN {siren}")
    if naf:
        meta_parts.append(f"NAF {naf}")
    if category:
        meta_parts.append(category)
    if headcount:
        meta_parts.append(f"{headcount} salariés")
    if city:
        meta_parts.append(city)
    if meta_parts:
        lines.append("  ".join(meta_parts))
    return "\n".join(lines)


def _eval_section(payload: dict) -> str:  # type: ignore[type-arg]
    score = payload.get("score", "")
    fit = payload.get("fit", "")
    dealbreakers: list[str] = payload.get("dealbreakers", [])
    uncertainty = payload.get("uncertainty", "")

    label = _SCORE_LABEL.get(score, score)
    parts = [f"## Eval  {label}"]
    if fit:
        parts.append(fit)
    if dealbreakers:
        parts.append("Dealbreakers: " + ", ".join(dealbreakers))
    if uncertainty:
        parts.append(f"Uncertainty: {uncertainty}")
    return "\n".join(parts)


def node_view(
    vault: Vault,
    summary_uri: str,
    siren_uri: str | None = None,
    eval_uri: str | None = None,
) -> str:
    """Return a markdown string summarising available data for a node.

    summary_uri is mandatory. siren_uri and eval_uri are optional.
    """
    sections: list[str] = []

    if siren_uri:
        try:
            sections.append(_siren_section(vault.load(siren_uri).decode()))
        except Exception:
            pass

    try:
        sum_data = json.loads(vault.load(summary_uri).decode())
        summary = sum_data.get("summary", "").strip()
        if summary:
            sections.append(f"## Summary\n\n{summary}")
    except Exception:
        pass

    if eval_uri:
        try:
            payload = json.loads(vault.load(eval_uri).decode())
            sections.append(_eval_section(payload))
        except Exception:
            pass

    if not sections:
        return "*(no data)*"

    return "\n\n---\n\n".join(sections)
