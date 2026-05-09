"""LLM eval step — scores a node summary against the user profile."""

from __future__ import annotations

import hashlib

from pydantic import BaseModel

from anpe.clients.mistral import mistral_run

_SYSTEM = """\
You are a job-search assistant helping a tech professional evaluate whether a French
company is worth approaching.

You receive:
- The user's search profile (what they are looking for, dealbreakers, context).
- A company summary produced from public data.

Your job: score the company against the profile and explain the deciding factor.

Score values:
- "good"    — clear match with the profile.
- "maybe"   — matches on most points but something is uncertain or incomplete.
- "discard" — clear non-match (dealbreaker present, or clearly out of scope).
- "enrich"  — a specific piece of information is missing that would change the score.
              Name the gap precisely in `fit`. Do NOT use this as a fallback when
              data is merely thin — use "maybe" with uncertainty "high" instead.

Rules:
- `fit`: one sentence naming the single deciding factor. This is what the user
  will read to validate or override your score — make it specific and factual.
- `dealbreakers`: list the profile dealbreakers that fired (may be empty).
- `uncertainty`: "low" | "medium" | "high". Reflects confidence in the score,
  not the completeness of the summary.
- Do not invent information not present in the summary.
- Do not hedge by defaulting to "maybe" — commit to a score.
"""

_MODEL_NAME = "mistral-small-2603"

EVAL_VERSION = hashlib.sha1(
    (_SYSTEM + _MODEL_NAME).encode()
).hexdigest()[:6]


class EvalResult(BaseModel):
    score: str  # "good" | "maybe" | "discard" | "enrich"
    fit: str
    dealbreakers: list[str]
    uncertainty: str  # "low" | "medium" | "high"


async def llm_eval(summary: str, profile: str) -> EvalResult:
    """Call the LLM to score a company summary against the user profile."""
    user_prompt = f"## User profile\n\n{profile}\n\n## Company summary\n\n{summary}"
    return await mistral_run(EvalResult, _MODEL_NAME, _SYSTEM, user_prompt)
