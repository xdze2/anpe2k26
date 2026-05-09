"""Mistral API client — structured completion with retry."""

from __future__ import annotations

import asyncio
import json
from typing import TypeVar

from pydantic import BaseModel

from mistralai.client import Mistral
from mistralai.client.errors import SDKError
from mistralai.client.models import ResponseFormat

from anpe.config import settings

_client = Mistral(api_key=settings.mistral_api_key)

MAX_RETRIES = 3
_RETRY_BASE_DELAY = 10.0

T = TypeVar("T", bound=BaseModel)


class LLMCapacityError(RuntimeError):
    """Quota exhausted or service tier exceeded — unretryable."""


class LLMCreditsError(RuntimeError):
    """No credits (HTTP 402) — top up account."""


async def mistral_run(
    output_type: type[T],
    model: str,
    system: str,
    prompt: str,
) -> T:
    """Call Mistral in JSON mode and return a validated output_type instance.

    Retries on transient 429s (rate limit). Raises LLMCapacityError on quota
    exhaustion (3505) and LLMCreditsError on 402 — both unretryable.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = await _client.chat.complete_async(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                response_format=ResponseFormat(type="json_object"),
            )
            content = response.choices[0].message.content  # type: ignore[union-attr]
            if content is None:
                raise RuntimeError("Mistral returned an empty response")
            return output_type.model_validate(json.loads(content))  # type: ignore[arg-type]
        except SDKError as e:
            if e.status_code == 402:
                raise LLMCreditsError(
                    "No LLM credits — top up at https://console.mistral.ai/"
                ) from e
            if e.status_code == 429:
                body = e.body or ""
                if "3505" in body or "service_tier_capacity_exceeded" in body:
                    raise LLMCapacityError(
                        f"Mistral capacity exceeded (3505) — quota exhausted for model {model!r}"
                    ) from e
                delay = _RETRY_BASE_DELAY * (2**attempt)
                print(
                    f"[mistral] rate-limited (429), retrying in {delay:.0f}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})"
                )
                await asyncio.sleep(delay)
                last_error = e
                continue
            raise

    raise RuntimeError(f"Mistral call failed after {MAX_RETRIES} retries") from last_error
