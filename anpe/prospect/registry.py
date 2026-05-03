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
    process: Callable[[str, str], Awaitable[EnrichResult]]
    raw_ext: str = "txt"
    capture_prompt: bool = False


FETCH_TOOLS: dict[str, FetchTool] = {
    "ddg": FetchTool(fetch=ddg_search, process=llm_summarize, capture_prompt=True),
    "siren": FetchTool(fetch=siren_fetch, process=siren_process, raw_ext="json"),
    # "fetch": FetchTool(fetch=http_fetch, process=llm_summarize),  # deferred
    # "tavily": FetchTool(fetch=tavily_fetch, process=llm_summarize),  # deferred
}
