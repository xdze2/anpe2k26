"""Registry of fetch tools available to the enrichment pipeline.

Each tool has signature: (target: str) -> str
It receives a query string or URL and returns raw text.
It raises on failure (network error, no results, …).
"""

from __future__ import annotations

from collections.abc import Callable

from anpe.enrich.tools.ddg import ddg_search

FETCH_TOOLS: dict[str, Callable[[str], str]] = {
    "ddg": ddg_search,
    # "siren":  siren_fetch,   # deferred
    # "fetch":  http_fetch,    # deferred
    # "tavily": tavily_fetch,  # deferred
}
