"""NAF code tools: bidirectional lookup between codes and activity descriptions."""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from pydantic_ai import Agent

_DATA = Path(__file__).parent.parent / "data"
_NAF_CSV = _DATA / "naf_codes.csv"


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


def register_naf_tools(agent: Agent) -> None:
    @agent.tool_plain
    def naf_lookup(code: str) -> str:
        """Return the label for a known NAF code.

        Use this when the user mentions a specific NAF code and wants to know
        what activity it corresponds to.

        Args:
            code: NAF code to look up, e.g. '71.12B' or '6201Z'.
        """
        normalized = code.strip().upper().replace(" ", "")
        if "." not in normalized:
            normalized = re.sub(r"^(\d{2})(\d)", r"\1.\2", normalized)
        index = _load_csv_index()
        label = index.get(normalized)
        if not label:
            return f"Code NAF '{code}' introuvable."
        return f"Code {normalized} — {label}"

    @agent.tool_plain
    def naf_search(keywords: str) -> str:
        """Find NAF codes matching a description of an activity or sector.

        Use this when the user describes a type of company, job domain, or
        sector and wants to know which NAF codes correspond to it.

        Args:
            keywords: Free-text description of the activity or sector,
                      e.g. 'engineering and AI' or 'data processing startup'.
        """
        index = _load_csv_index()
        words = [w for w in keywords.lower().split() if len(w) > 2]

        scored: list[tuple[int, str, str]] = []
        for code, label in index.items():
            label_lower = label.lower()
            score = sum(1 for w in words if w in label_lower)
            if score > 0:
                scored.append((score, code, label))

        scored.sort(key=lambda x: -x[0])
        top = scored[:10]

        if not top:
            return f"Aucun code NAF trouvé pour « {keywords} »."

        lines = [f"Codes NAF correspondant à « {keywords} » :"]
        for _, code, label in top:
            lines.append(f"  {code}  {label}")
        return "\n".join(lines)
