"""LLM summarization step for the enrichment pipeline."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from anpe.config import settings

_INTENT = "We are looking for small French tech companies doing AI or software work."

_SYSTEM = """\
You are an enrichment assistant. You receive raw data fetched about a company and a
previous summary (may be empty). Your job is to produce an updated summary and decide
what to fetch next.

Current search intent:
{intent}

Rules:
- status "ok": data was useful, summary updated.
- status "not_relevant": company clearly does not match the intent, stop here.
- status "no_data": fetch returned nothing actionable, continue if queue has more.
- new_targets: list of (tool, target) pairs worth fetching next.
  Only propose targets you actually found in the data (URLs, names).
  Use tool "ddg" for search queries, "fetch" for direct URLs.
  Keep the list short (0-3 items). Empty list is fine.
- summary: markdown, under 300 words, synthesize don't accumulate.
  Write in English.
""".format(intent=_INTENT)


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


async def llm_summarize(raw_data: str, previous_summary: str) -> EnrichResult:
    prompt = ""
    if previous_summary:
        prompt += f"## Previous summary\n\n{previous_summary}\n\n"
    prompt += f"## New data\n\n{raw_data}"

    result = await _agent.run(prompt)
    return result.output
