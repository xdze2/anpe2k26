"""DuckDuckGo text search client."""

from __future__ import annotations

import json

from ddgs import DDGS

from anpe.clients.errors import FetchBlockedError, FetchNotFoundError, FetchRetryableError
from anpe.clients.rate_limiter import RateLimiter


def _ddg_search(query: str, max_results: int = 10) -> str:
    """Search DDG for query. Returns raw JSON string.

    Raises FetchNotFoundError on empty results, FetchBlockedError on
    Cloudflare/CAPTCHA, FetchRetryableError on transient errors.
    """
    try:
        results = DDGS().text(query, max_results=max_results, region="fr-fr")
    except Exception as e:
        msg = str(e).lower()
        if "ratelimit" in msg or "202" in msg:
            raise FetchRetryableError(f"DDG rate limit: {e}") from e
        if "blocked" in msg or "cloudflare" in msg or "captcha" in msg:
            raise FetchBlockedError(f"DDG blocked: {e}") from e
        raise FetchRetryableError(f"DDG error: {e}") from e

    if not results:
        raise FetchNotFoundError(f"DDG returned no results for: {query!r}")
    return json.dumps(results, ensure_ascii=False, indent=2)


ddg_client = RateLimiter(_ddg_search, min_interval_s=2.0)
