"""NAF code tools: bidirectional lookup between codes and activity descriptions."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

import yaml
from pydantic_ai import Agent

_DOCS = Path(__file__).parent.parent.parent / "docs" / "siren_infos"
_NAF_CSV = _DOCS / "naf_codes.csv"
_NAF_CATEGORIES_YAML = _DOCS / "naf_categories.yaml"


class _NafEntry(TypedDict):
    code: str
    label: str


class _NafCategory(TypedDict):
    description: str
    codes: list[_NafEntry]


@lru_cache(maxsize=1)
def _load_csv_index() -> dict[str, str]:
    """Map NAF code → full label (e.g. '71.12B' → 'Ingénierie, études techniques')."""
    index: dict[str, str] = {}
    with open(_NAF_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["Code"].strip()
            label = row[" Intitulés de la  NAF rév. 2, version finale "].strip()
            if code and label:
                index[code] = label
    return index


@lru_cache(maxsize=1)
def _load_categories() -> dict[str, _NafCategory]:
    with open(_NAF_CATEGORIES_YAML, encoding="utf-8") as f:
        data: dict[str, _NafCategory] = yaml.safe_load(f)["categories"]
        return data


def register_naf_tools(agent: Agent) -> None:
    @agent.tool_plain
    def naf_lookup(code: str) -> str:
        """Return the label and category for a known NAF code.

        Use this when the user mentions a specific NAF code and wants to know
        what activity it corresponds to.

        Args:
            code: NAF code to look up, e.g. '71.12B' or '6201Z'.
        """
        normalized = code.strip().upper().replace(" ", "")
        # accept both '71.12B' and '7112B' formats
        if "." not in normalized:
            normalized = normalized[:2] + "." + normalized[2:]
        index = _load_csv_index()
        label = index.get(normalized)
        if not label:
            return f"Code NAF '{code}' introuvable."

        categories = _load_categories()
        for cat_name, cat in categories.items():
            for entry in cat["codes"]:
                if entry["code"].replace(".", "").upper() == normalized.replace(".", "").upper():
                    return (
                        f"Code {code} — {label}\n"
                        f"Catégorie : {cat_name} ({cat['description']})"
                    )

        return f"Code {code} — {label}"

    @agent.tool_plain
    def naf_search(keywords: str) -> str:
        """Find NAF codes matching a description of an activity or sector.

        Use this when the user describes a type of company, job domain, or
        sector and wants to know which NAF codes correspond to it.
        Returns matching categories with their codes and labels so you can
        identify the most relevant ones.

        Args:
            keywords: Free-text description of the activity or sector,
                      e.g. 'engineering and AI' or 'data processing startup'.
        """
        categories = _load_categories()
        kw_lower = keywords.lower()

        # Score each category by keyword overlap
        scored: list[tuple[int, str, _NafCategory]] = []
        for cat_name, cat in categories.items():
            score = 0
            searchable = (cat_name + " " + cat["description"]).lower()
            for word in kw_lower.split():
                if len(word) > 2 and word in searchable:
                    score += 2
            for entry in cat["codes"]:
                for word in kw_lower.split():
                    if len(word) > 2 and word in entry["label"].lower():
                        score += 1
            scored.append((score, cat_name, cat))

        scored.sort(key=lambda x: -x[0])

        # Return top matches (at least the best one, up to 3 non-zero)
        top = [x for x in scored if x[0] > 0][:3] or [scored[0]]

        lines = [f"Catégories NAF correspondant à « {keywords} » :\n"]
        for _, cat_name, cat in top:
            lines.append(f"## {cat_name} — {cat['description']}")
            for entry in cat["codes"]:
                lines.append(f"  {entry['code']}  {entry['label']}")
            lines.append("")

        return "\n".join(lines)
