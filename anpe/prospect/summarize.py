"""LLM summarization step for the enrichment pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from anpe.config import settings

_SYSTEM = """\
You are an enrichment assistant. You receive raw data fetched about a company and a
previous summary (may be empty). Your job is to produce an updated summary and decide
what to fetch next.

Rules:
- status "ok": data was useful, summary updated.
- status "not_relevant": the fetched data clearly belongs to a different entity than
  the company described in the previous summary (e.g. a disambiguation page, a person,
  an unrelated business). If the search query was too ambiguous, propose a more specific
  DDG query in new_targets so the pipeline can retry.
- status "no_data": fetch returned nothing actionable, continue if queue has more.
- new_targets: list of (tool, target) pairs worth fetching next.
  DDG results are snippets only — always propose the most relevant URLs as "fetch"
  targets so the pipeline can retrieve the full content. Priority order:
    1. Company's official website
    2. Wikipedia page (if one exists for the company)
    3. LinkedIn company page
    4. Business news article (e.g. Les Echos, Maddyness, Tech.eu, BFM Business)
  Propose all of them if found in the data (up to 4). Use tool "fetch" for URLs,
  "ddg" for new search queries.
  If status is "no_data", new_targets must be empty.
- summary: markdown, under 300 words, synthesize don't accumulate.
  Write in English.
"""

MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5.0  # seconds, doubles each attempt


class LLMCreditsError(RuntimeError):
    """Raised on HTTP 402 — no credits, unretryable."""


class FetchTarget(BaseModel):
    tool: str
    target: str


class EnrichResult(BaseModel):
    status: str  # "ok" | "not_relevant" | "no_data"
    summary: str
    new_targets: list[FetchTarget]


_model = OpenAIChatModel(
    settings.mistral_model,
    provider=OpenAIProvider(
        base_url=settings.mistral_base_url,
        api_key=settings.mistral_api_key,
    ),
)

_agent: Agent[None, EnrichResult] = Agent(
    _model,
    output_type=EnrichResult,
    system_prompt=_SYSTEM,
)


async def llm_summarize(
    raw_data: str, previous_summary: str, prompt_file: Path | None = None
) -> EnrichResult:
    prompt = ""
    if previous_summary:
        prompt += f"## Previous summary\n\n{previous_summary}\n\n"
    prompt += f"## New data\n\n{raw_data}"

    if prompt_file is not None:
        full = f"## System prompt\n\n{_SYSTEM}\n## User prompt\n\n{prompt}"
        prompt_file.write_text(full, encoding="utf-8")

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            result = await _agent.run(prompt)
            return result.output
        except Exception as e:
            msg = str(e)
            if "402" in msg:
                raise LLMCreditsError(
                    "No LLM credits — top up at https://console.mistral.ai/"
                ) from e
            if "429" in msg:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                print(f"[llm] rate-limited (429), retrying in {delay:.0f}s "
                      f"(attempt {attempt + 1}/{MAX_RETRIES})")
                await asyncio.sleep(delay)
                last_error = e
                continue
            raise

    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} retries") from last_error
