"""DuckDuckGo text search fetch tool."""

from __future__ import annotations

import json

from ddgs import DDGS

from anpe.clients.errors import FetchNotFoundError


def ddg_search(query: str, max_results: int = 10) -> str:
    results = DDGS().text(query, max_results=max_results, region="fr-fr")
    if not results:
        raise FetchNotFoundError(f"DDG returned no results for: {query!r}")
    return json.dumps(results, ensure_ascii=False, indent=2)
