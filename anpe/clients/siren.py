"""HTTP client for the recherche-entreprises.api.gouv.fr API."""

from __future__ import annotations

import httpx

from anpe.prospect.errors import FetchNotFoundError, FetchRetryableError

_SEARCH_URL = "https://recherche-entreprises.api.gouv.fr/search"


def siren_fetch(number: str) -> str:
    """Fetch company data by SIREN (9 digits) or SIRET (14 digits).

    Returns raw JSON as a string. Raises FetchNotFoundError on no results,
    FetchRetryableError on transient network errors.
    """
    import json

    number = number.strip().replace(" ", "")
    if len(number) not in (9, 14) or not number.isdigit():
        raise FetchNotFoundError(f"SIREN: {number!r} is not a valid SIREN (9 digits) or SIRET (14 digits)")
    try:
        response = httpx.get(
            _SEARCH_URL,
            params={"q": number, "per_page": 1},
            timeout=10.0,
            headers={"Accept": "application/json"},
        )
    except httpx.TransportError as e:
        raise FetchRetryableError(f"SIREN network error: {e}") from e

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

    return json.dumps(result)
