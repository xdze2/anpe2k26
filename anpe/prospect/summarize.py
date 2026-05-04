"""LLM summarization step for the enrichment pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
from urllib.parse import urlparse

from pydantic_ai import Agent
from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider

from anpe.config import settings

from anpe.prospect.types import (
    FetchTarget,
    SummarizeResult,
)  # noqa: F401  (re-exported)

DIRECTORY_BLACKLIST = {
    # French company registries & legal directories
    "societe.com",
    "verif.com",
    "sirene.data.gouv.fr",
    "infogreffe.fr",
    "pagesjaunes.fr",
    "kompass.com",
    "europages.fr",
    "pappers.fr",
    "infonet.fr",
    "lagazettefrance.fr",
    "hoodspot.fr",
    "eterritoire.fr",
    "annuairefrancais.fr",
    "datalegal.fr",
    "codes-naf.com",
    "rubypayeur.com",
    "manageo.fr",
    "legalin.fr",
    "adr-st-o.com",
    "mappy.com",
    "grokipedia.com",
    "youtube.com",
    "pinterest.com",
    "alibaba.com",
    # Professional networks
    "viadeo.com",
    "viadeo.journaldunet.com",
    # Startup & company aggregators
    "crunchbase.com",
    "airsaas.io",
    "sortlist.com",
    "motherbase.io",
    # Job boards
    "jooble.org",
    "jobteaser.com",
}


_SYSTEM = """\
You are a job-search prospecting assistant. You help build intelligence dossiers on
French PME/ETI companies that a tech professional might want to approach for employment.

You receive:
- A "Company profile" block (ground truth from the SIREN registry — treat it as
  authoritative: name, SIREN, sector, size, city).
- A previous summary (may be empty).
- New raw data freshly fetched about the company.

Your job: produce an updated summary and decide what to fetch next.

Rules:

- status "ok": new data was useful, summary updated.

- status "not_relevant": use when EITHER:
    a) The fetched data clearly belongs to a different entity (disambiguation page,
       wrong company, unrelated person or business). Propose a more specific DDG query
       in new_targets so the pipeline can retry with a better search.
    b) The company is out of scope for job prospecting: large group (GE, 10 000+
       employees), multinational, public sector, or unrelated industry (defence,
       utilities, mass retail…). Ground truth for this is the Company profile block
       — if Category is "GE" or Headcount is "10 000+", always use case (b).
       Leave new_targets empty — no point continuing.

- status "no_data": fetch returned nothing actionable, continue if queue has more.
  new_targets MUST be empty — do NOT suggest DDG queries or URLs to compensate.

- new_targets: list of (tool, target) pairs worth fetching next.
  DDG results are snippets only — always propose the most relevant URLs as "fetch"
  targets so the pipeline can retrieve the full content. Priority order:
    1. Company's official website
    2. Wikipedia page (if one exists for the company)
    3. LinkedIn company page
    4. Business news article (e.g. Les Echos, Maddyness, Tech.eu, BFM Business)
  Propose all found in the data (up to 4). Use tool "fetch" for URLs, "ddg" for
  new search queries.

- summary: markdown, under 300 words, synthesize don't accumulate. English.
  Do not repeat information already in the Company profile block.
  Do not add filler sections like "Key insights", "Key takeaway", "Next steps",
  "Potential fit", or any closing sentence about why the company "appeals to tech
  professionals" — that judgement belongs to the user, not the summary.

  Start the summary with a single compact header line:
    **Type**: <nature of activity — e.g. éditeur logiciel, ESN/prestataire, agence,
              conseil, industrie avec DSI interne> · **Domaine**: <business or tech
              sector — e.g. e-commerce, cybersécurité, RH, mobilité, spatial> ·
              **Marché**: <who are the clients — B2B, B2C, B2G, mixte>
  Leave a field empty if the data does not support a confident answer.
  The rest of the summary contains only what is not already obvious from that header
  line or from the Company profile block.
"""

_MODEL_NAME = "mistral-small-2603"
_BLACKLIST_KEY = ",".join(sorted(DIRECTORY_BLACKLIST))
SUMMARIZE_VERSION = hashlib.sha1((_SYSTEM + _MODEL_NAME + _BLACKLIST_KEY).encode()).hexdigest()[:6]

MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5.0  # seconds, doubles each attempt


class LLMCreditsError(RuntimeError):
    """Raised on HTTP 402 — no credits, unretryable."""


_model = MistralModel(
    _MODEL_NAME,
    provider=MistralProvider(api_key=settings.mistral_api_key),
)

_agent: Agent[None, SummarizeResult] = Agent(
    _model,
    output_type=SummarizeResult,
    system_prompt=_SYSTEM,
)


def _format_ddg_results(raw_json: str) -> str:
    results = json.loads(raw_json)
    lines: list[str] = []
    for r in results:
        href = r.get("href", "")
        domain = urlparse(href).hostname or ""
        if domain in DIRECTORY_BLACKLIST:
            continue
        lines.append(r.get("title", ""))
        lines.append(href)
        lines.append(r.get("body", ""))
        lines.append("")
    return "\n".join(lines)


async def ddg_summarize(
    raw_data: str,
    previous_summary: str,
    company_profile: str = "",
) -> SummarizeResult:
    user_prompt = ""
    if company_profile:
        user_prompt += f"## Company profile\n\n{company_profile}\n\n"
    if previous_summary:
        user_prompt += f"## Previous summary\n\n{previous_summary}\n\n"
    user_prompt += f"## New data\n\n{_format_ddg_results(raw_data)}"

    full_prompt = f"## System prompt\n\n{_SYSTEM}\n## User prompt\n\n{user_prompt}"

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            result = await _agent.run(user_prompt)
            output = result.output
            output.prompt = full_prompt
            output.version = SUMMARIZE_VERSION
            output.model = _MODEL_NAME
            return output
        except Exception as e:
            msg = str(e)
            if "402" in msg:
                raise LLMCreditsError(
                    "No LLM credits — top up at https://console.mistral.ai/"
                ) from e
            if "429" in msg:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                print(
                    f"[llm] rate-limited (429), retrying in {delay:.0f}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})"
                )
                await asyncio.sleep(delay)
                last_error = e
                continue
            raise

    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} retries") from last_error
