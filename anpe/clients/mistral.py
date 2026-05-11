"""Mistral API client — structured completion."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from mistralai.client import Mistral
from mistralai.client.errors import SDKError
from mistralai.client.models import ResponseFormat

from anpe.clients.rate_limiter import RateLimiter
from anpe.config import settings

T = TypeVar("T", bound=BaseModel)


class LLMCapacityError(RuntimeError):
    """Quota exhausted or service tier exceeded."""


class LLMCreditsError(RuntimeError):
    """No credits (HTTP 402) — top up account."""


_sdk = Mistral(api_key=settings.mistral_api_key)


def _mistral_complete(model: str, messages: list[dict[str, str]]) -> str:  # type: ignore[type-arg]
    try:
        response = _sdk.chat.complete(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            response_format=ResponseFormat(type="json_object"),
        )
    except SDKError as e:
        if e.status_code == 402:
            raise LLMCreditsError("No LLM credits — top up at https://console.mistral.ai/") from e
        if e.status_code == 429:
            body = e.body or ""
            if "3505" in body or "service_tier_capacity_exceeded" in body:
                raise LLMCapacityError(f"Mistral capacity exceeded (3505) — quota exhausted for model {model!r}") from e
        raise

    content = response.choices[0].message.content  # type: ignore[union-attr]
    if content is None:
        raise RuntimeError("Mistral returned an empty response")
    return content


mistral_complete = RateLimiter(_mistral_complete, min_interval_s=1.0)


def mistral_run(output_type: type[T], model: str, system: str, prompt: str) -> T:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    content = mistral_complete(model, messages)
    return output_type.model_validate(json.loads(content))
