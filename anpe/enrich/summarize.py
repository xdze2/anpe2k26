"""LLM summarization step for the enrichment pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from anpe.config import settings

_INTENT = "We are looking for small French tech companies doing AI or software work."

_SYSTEM = f"""\
You are an enrichment assistant. You receive raw data fetched about a company and a
previous summary (may be empty). Your job is to produce an updated summary and decide
what to fetch next.

Current search intent:
{_INTENT}

Rules:
- status "ok": data was useful, summary updated.
- status "not_relevant": company clearly does not match the intent, stop here.
- status "no_data": fetch returned nothing actionable, continue if queue has more.
- new_targets: list of (tool, target) pairs worth fetching next.
  Only propose targets you actually found in the data (URLs, names).
  Use tool "ddg" for search queries, "fetch" for direct URLs.
  Keep the list short (0-3 items). Empty list is fine.
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
    settings.openrouter_model,
    provider=OpenAIProvider(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
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
        prompt_file.write_text(prompt, encoding="utf-8")

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            result = await _agent.run(prompt)
            return result.output
        except Exception as e:
            msg = str(e)
            if "402" in msg:
                raise LLMCreditsError(
                    "No LLM credits — top up at https://openrouter.ai/settings/credits"
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
