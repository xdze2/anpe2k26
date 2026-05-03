# 2026-05-03 — Bootstrap implementation

## What was built

Full implementation of `anpe bootstrap run` as specced in `docs/specs/32_bootstrap_using_siren.md`.

### New structure

```
anpe/clients/siren.py          HTTP client for recherche-entreprises API (extracted from enrich/)
anpe/bootstrap/filter.py       Pure helpers: haversine_km, within_radius, tranche_in_range
anpe/bootstrap/search.py       Paginated API fetcher with per-page file cache
anpe/bootstrap/pipeline.py     7-step sequence: load profile → fetch → extract → filter → dedup → CSV
```

### Cache design

Per-page JSONL files: `cache_data/bootstrap_cache/dep31_naf6201Z_p001.jsonl`, `_p002.jsonl`, …
A `.done` sentinel marks a pair as fully fetched — avoids an extra API call on resume.
Kill-safe: each page is written immediately after the HTTP response. A killed run resumes
from the first missing page on the next invocation.
`--refresh` deletes all page files and the sentinel, then re-fetches from scratch.

### Layout decisions

- `anpe/clients/` for API HTTP clients — avoids confusion with pydantic-ai agent tools
- `cache_data/` separate from `user_data/` — prevents accidental deletion of user data
- `user_data/user_profile.yaml` — profile lives alongside other user data, not at project root
- Pure helpers (haversine, headcount bands) kept inline in `bootstrap/filter.py` — only bootstrap needs them

### Command

```bash
anpe bootstrap run           # fetch + filter + write user_data/company_listing.csv
anpe bootstrap run --refresh # invalidate cache and re-fetch all pairs
```

Reads `user_data/user_profile.yaml`. Writes `user_data/company_listing.csv`.

## Tests added

`tests/test_bootstrap_filter.py` — 8 unit tests for the pure filter functions.

## Next

- Run a full fetch and validate the output CSV
- Wire `user_data/company_listing.csv` as input to the enrichment pipeline (replacing manual seeds)
