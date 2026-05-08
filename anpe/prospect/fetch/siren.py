"""Recherche Entreprises API fetch tool — re-exports siren_fetch from anpe.clients.siren."""

from __future__ import annotations

from anpe.clients.siren import siren_fetch

__all__ = ["siren_fetch"]
