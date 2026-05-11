"""DuckDuckGo text search fetch tool."""

from __future__ import annotations

import json
import time

from ddgs import DDGS

from anpe.clients.errors import FetchBlockedError, FetchNotFoundError, FetchRetryableError


class DdgClient:
    """Search DuckDuckGo with a rate limit."""

    def __init__(self, min_interval_s: float = 2.0) -> None:
        self._min_interval = min_interval_s
        self._last_call: float = 0.0

    def __call__(self, query: str, max_results: int = 10) -> str:
        """Search DDG for query. Returns raw JSON string.

        Raises FetchNotFoundError on empty results, FetchBlockedError on
        Cloudflare/CAPTCHA, FetchRetryableError on transient errors.
        """
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)

        try:
            results = DDGS().text(query, max_results=max_results, region="fr-fr")
        except Exception as e:
            msg = str(e).lower()
            if "ratelimit" in msg or "202" in msg:
                raise FetchRetryableError(f"DDG rate limit: {e}") from e
            if "blocked" in msg or "cloudflare" in msg or "captcha" in msg:
                raise FetchBlockedError(f"DDG blocked: {e}") from e
            raise FetchRetryableError(f"DDG error: {e}") from e
        finally:
            self._last_call = time.monotonic()

        if not results:
            raise FetchNotFoundError(f"DDG returned no results for: {query!r}")
        return json.dumps(results, ensure_ascii=False, indent=2)
