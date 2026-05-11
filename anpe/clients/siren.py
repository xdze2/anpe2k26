"""HTTP client for the recherche-entreprises.api.gouv.fr API."""

from __future__ import annotations

import json
import time

import httpx

from anpe.clients.errors import FetchNotFoundError, FetchRetryableError

_SEARCH_URL = "https://recherche-entreprises.api.gouv.fr/search"


class SirenClient:
    """Fetch company data from the Recherche Entreprises API with a rate limit."""

    def __init__(self, min_interval_s: float = 1.0) -> None:
        self._min_interval = min_interval_s
        self._last_call: float = 0.0

    def __call__(self, number: str) -> str:
        """Fetch company data by SIREN (9 digits) or SIRET (14 digits).

        Returns raw JSON as a string. Raises FetchNotFoundError on no results,
        FetchRetryableError on transient network errors.
        """
        number = number.strip().replace(" ", "")
        if len(number) not in (9, 14) or not number.isdigit():
            raise FetchNotFoundError(f"SIREN: {number!r} is not a valid SIREN (9 digits) or SIRET (14 digits)")

        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)

        try:
            response = httpx.get(
                _SEARCH_URL,
                params={"q": number, "per_page": 1},
                timeout=10.0,
                headers={"Accept": "application/json"},
            )
        except httpx.TransportError as e:
            raise FetchRetryableError(f"SIREN network error: {e}") from e
        finally:
            self._last_call = time.monotonic()

        if response.status_code == 429:
            raise FetchRetryableError(f"SIREN rate limit (429) for {number!r}")
        elif response.status_code >= 500:
            raise FetchRetryableError(f"SIREN server error {response.status_code} for {number!r}")

        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])
        if not results:
            raise FetchNotFoundError(f"SIREN: no company found for {number!r}")

        result = results[0]
        if len(number) == 9 and result.get("siren", "") != number:
            raise FetchNotFoundError(f"SIREN: no company found for SIREN {number!r}")
        if len(number) == 14 and result.get("siege", {}).get("siret", "") != number:
            raise FetchNotFoundError(f"SIREN: no company found for SIRET {number!r}")

        return json.dumps(result, ensure_ascii=False, indent=2)
