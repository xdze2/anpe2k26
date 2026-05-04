"""Registry of fetch tools available to the enrichment pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from anpe.prospect.fetch.ddg import ddg_search
from anpe.prospect.fetch.siren import siren_fetch, siren_summarize
from anpe.prospect.summarize import ddg_summarize
from anpe.prospect.types import SummarizeResult


@dataclass
class FetchTool:
    fetch: Callable[[str], str]
    summarize: Callable[[str, str, str], Awaitable[SummarizeResult]]
    raw_ext: str = "txt"


FETCH_TOOLS: dict[str, FetchTool] = {
    "ddg": FetchTool(fetch=ddg_search, summarize=ddg_summarize),
    "siren": FetchTool(fetch=siren_fetch, summarize=siren_summarize, raw_ext="json"),
    # "fetch": FetchTool(fetch=http_fetch, summarize=ddg_summarize),  # deferred
    # "tavily": FetchTool(fetch=tavily_fetch, summarize=ddg_summarize),  # deferred
}
