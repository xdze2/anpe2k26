"""Registry of fetch tools available to the enrichment pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from anpe.prospect.fetch.ddg import ddg_search
from anpe.prospect.fetch.siren import SIREN_SUMMARIZE_VERSION, siren_fetch, siren_summarize
from anpe.prospect.summarize import SUMMARIZE_VERSION, ddg_summarize
from anpe.prospect.types import SummarizeResult


@dataclass
class FetchTool:
    fetch: Callable[[str], str]
    summarize: Callable[[str, str, str], Awaitable[SummarizeResult]]
    version: str  # summarize_version written to sum_*.json; bump when prompt or model changes
    raw_ext: str = "txt"


FETCH_TOOLS: dict[str, FetchTool] = {
    "ddg": FetchTool(fetch=ddg_search, summarize=ddg_summarize, version=SUMMARIZE_VERSION, raw_ext="json"),
    "siren": FetchTool(fetch=siren_fetch, summarize=siren_summarize, version=SIREN_SUMMARIZE_VERSION, raw_ext="json"),
    # "fetch": FetchTool(fetch=http_fetch, summarize=ddg_summarize),  # deferred
    # "tavily": FetchTool(fetch=tavily_fetch, summarize=ddg_summarize),  # deferred
}
