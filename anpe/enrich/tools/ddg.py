"""DuckDuckGo text search fetch tool."""

from __future__ import annotations

from ddgs import DDGS


def ddg_search(query: str, max_results: int = 10) -> str:
    """Search DuckDuckGo and return results as plain text.

    Raises RuntimeError if no results are returned.
    """
    results = DDGS().text(query, max_results=max_results, region="fr-fr")
    if not results:
        raise RuntimeError(f"DDG returned no results for: {query!r}")

    lines: list[str] = []
    for r in results:
        lines.append(r.get("title", ""))
        lines.append(r.get("href", ""))
        lines.append(r.get("body", ""))
        lines.append("")
    return "\n".join(lines)
