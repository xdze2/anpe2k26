"""Node ID utilities for prospect nodes."""

from __future__ import annotations

import re
import unicodedata


def slugify(text: str) -> str:
    """Lowercase, strip accents, replace non-alphanumeric runs with '_'."""
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    return slug


def node_id_for(nom_complet: str, siren: str) -> str:
    return f"{slugify(nom_complet)}_{siren}"
