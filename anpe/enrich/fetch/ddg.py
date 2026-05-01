"""DuckDuckGo text search fetch tool."""

from __future__ import annotations

from ddgs import DDGS

from anpe.enrich.errors import FetchNotFoundError


def ddg_search(query: str, max_results: int = 10) -> str:
    results = DDGS().text(query, max_results=max_results, region="fr-fr")
    if not results:
        raise FetchNotFoundError(f"DDG returned no results for: {query!r}")

    lines: list[str] = []
    for r in results:
        lines.append(r.get("title", ""))
        lines.append(r.get("href", ""))
        lines.append(r.get("body", ""))
        lines.append("")
    return "\n".join(lines)
