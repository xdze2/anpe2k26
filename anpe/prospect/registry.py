"""Registry of fetch tools available to the enrichment pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from anpe.prospect.fetch.ddg import ddg_search
from anpe.prospect.fetch.siren import siren_fetch, siren_process
from anpe.prospect.summarize import EnrichResult, llm_summarize


@dataclass
class FetchTool:
    fetch: Callable[[str], str]
    summarize: Callable[[str, str, str], Awaitable[EnrichResult]]
    raw_ext: str = "txt"


FETCH_TOOLS: dict[str, FetchTool] = {
    "ddg": FetchTool(fetch=ddg_search, summarize=llm_summarize),
    "siren": FetchTool(fetch=siren_fetch, summarize=siren_process, raw_ext="json"),
    # "fetch": FetchTool(fetch=http_fetch, summarize=llm_summarize),  # deferred
    # "tavily": FetchTool(fetch=tavily_fetch, summarize=llm_summarize),  # deferred
}
