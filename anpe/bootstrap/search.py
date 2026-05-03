"""Paginated search against recherche-entreprises API with per-page file cache.

Each (departement, naf_code) pair is cached as one JSON file per page under
user_data/bootstrap_cache/. Files are written immediately after each request,
so a killed run resumes from the last completed page.

Cache files:
  dep31_naf6201Z_p001.json
  dep31_naf6201Z_p002.json
  ...

A pair is considered complete when a sentinel file dep31_naf6201Z.done exists.
On resume, already-cached pages are skipped and fetching continues from where
it left off.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

_SEARCH_URL = "https://recherche-entreprises.api.gouv.fr/search"
_PER_PAGE = 25
_LIMIT_MATCHING = 100
_REQUEST_DELAY = 0.15  # seconds between paginated requests — stays under 7 req/s

logger = logging.getLogger(__name__)


def _pair_slug(departement: str, naf_code: str) -> str:
    naf_slug = naf_code.replace(".", "").replace(" ", "")
    return f"dep{departement}_naf{naf_slug}"


def _page_path(cache_dir: Path, slug: str, page: int) -> Path:
    return cache_dir / f"{slug}_p{page:03d}.jsonl"


def _done_path(cache_dir: Path, slug: str) -> Path:
    return cache_dir / f"{slug}.done"


def _load_cached_pages(cache_dir: Path, slug: str) -> list[dict]:
    """Load and concatenate all cached page files for a slug."""
    results: list[dict] = []
    page = 1
    while True:
        p = _page_path(cache_dir, slug, page)
        if not p.exists():
            break
        results.extend(json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line)
        page += 1
    return results


def fetch_pair(
    departement: str,
    naf_code: str,
    etat: str,
    cache_dir: Path,
    refresh: bool = False,
) -> list[dict]:
    """Return raw API results for (departement, naf_code).

    Pages are cached individually as they arrive. If a previous run was
    interrupted, fetching resumes from the first missing page.
    Pass refresh=True to delete all cached pages and re-fetch from scratch.
    """
    slug = _pair_slug(departement, naf_code)
    done_file = _done_path(cache_dir, slug)

    if refresh:
        for f in cache_dir.glob(f"{slug}_p*.jsonl"):
            f.unlink()
        if done_file.exists():
            done_file.unlink()

    if done_file.exists():
        results = _load_cached_pages(cache_dir, slug)
        logger.info("Cache hit: dep=%s naf=%s (%d results)", departement, naf_code, len(results))
        return results

    # Find the first page not yet cached to support resume after kill.
    cache_dir.mkdir(parents=True, exist_ok=True)
    start_page = 1
    while _page_path(cache_dir, slug, start_page).exists():
        start_page += 1

    if start_page > 1:
        logger.info("Resuming dep=%s naf=%s from page %d", departement, naf_code, start_page)
    else:
        logger.info("Fetching dep=%s naf=%s ...", departement, naf_code)

    total_pages: int | None = None
    page = start_page

    while True:
        params = {
            "departement": departement,
            "activite_principale": naf_code,
            "etat_administratif": etat,
            "per_page": _PER_PAGE,
            "limite_matching_etablissements": _LIMIT_MATCHING,
            "page": page,
        }
        response = httpx.get(
            _SEARCH_URL,
            params=params,
            timeout=15.0,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

        page_results = data.get("results", [])

        # Save this page immediately.
        _page_path(cache_dir, slug, page).write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in page_results),
            encoding="utf-8",
        )

        if total_pages is None:
            total_results = data.get("total_results", 0)
            total_pages = max(1, -(-total_results // _PER_PAGE))  # ceil division
            logger.info("  dep=%s naf=%s: %d results, %d pages", departement, naf_code, total_results, total_pages)
            if total_results >= 1000:
                logger.warning(
                    "  dep=%s naf=%s: total_results=%d may be truncated by API cap",
                    departement, naf_code, total_results,
                )

        if page >= total_pages or not page_results:
            break

        page += 1
        time.sleep(_REQUEST_DELAY)

    # Mark pair as complete.
    done_file.write_text("", encoding="utf-8")

    results = _load_cached_pages(cache_dir, slug)
    logger.info("  → %d total results for dep=%s naf=%s", len(results), departement, naf_code)
    return results
