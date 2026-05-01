# 2026-05-01 — SIREN fetch tool + pipeline refactor

## What changed

### New: fetch exception hierarchy (`anpe/enrich/errors.py`)

Three typed exceptions replacing bare `RuntimeError` for fetch failures:

| Exception | Meaning | Pipeline action |
|---|---|---|
| `FetchNotFoundError` | 404, empty result, no hits | log `not_found`, skip |
| `FetchRetryableError` | network error, rate limit | log `retryable` |
| `FetchBlockedError` | Cloudflare, CAPTCHA | log `blocked`, surface to user |

`ddg_search` now raises `FetchNotFoundError` on empty results (was `RuntimeError`).

### New: `FetchTool` dataclass in registry

Each entry in `FETCH_TOOLS` now carries both a `fetch` function and a `process`
function, decoupling the two steps:

```python
@dataclass
class FetchTool:
    fetch: Callable[[str], str]
    process: Callable[[str, str], EnrichResult | Awaitable[EnrichResult]]
    raw_ext: str = "txt"
```

This was the key design gap that adding SIREN exposed: some tools don't need an LLM
to produce a summary — a deterministic formatter is enough. `process` can be either
async (LLM path) or sync (formatter path); the pipeline handles both via
`inspect.isawaitable`.

`raw_ext` controls the file extension for the saved raw file (`"json"` for siren,
`"txt"` for everything else).

### Rename: `anpe/enrich/tools/` → `anpe/enrich/fetch/`

Clearer name — this directory contains fetch tool implementations, not generic tools.

### New: `anpe/enrich/fetch/siren.py`

Two functions:

**`siren_fetch(number)`** — calls `recherche-entreprises.api.gouv.fr/search` (public,
no API key). Accepts SIREN (9 digits) or SIRET (14 digits). Returns `results[0]` as
JSON string.

Key decisions:
- Used `recherche-entreprises.api.gouv.fr` (no auth) instead of `api.insee.fr` (requires
  bearer token). Found in `docs/references/siren_infos/openapi_recherche_entreprise.json`.
- The endpoint is a search, not a direct lookup — it returns close matches for invalid
  numbers. Added explicit exact-match check: compares `result["siren"]` (9-digit input)
  or `result["siege"]["siret"]` (14-digit input) against the input. Mismatch →
  `FetchNotFoundError`.
- Input validated upfront: must be exactly 9 or 14 digits, otherwise `FetchNotFoundError`
  before hitting the network.

**`siren_process(raw_data, previous_summary)`** — deterministic formatter, no LLM.
Produces a markdown summary card (name, SIREN, NAF, legal form, headcount band, creation
date, status, address) and always proposes one DDG follow-up using `siege.nom_commercial`
(falls back to `nom_complet` if absent — commercial name is cleaner for search).

### Pipeline updates (`anpe/enrich/pipeline.py`)

- `_run_summarize` renamed to `_run_process`, dispatches via `tool.process` instead of
  hardcoded `llm_summarize`.
- `_fetch` maps typed exceptions to status strings: `not_found`, `retryable`, `blocked`,
  `fetch_error`.
- `StepLog` extended: `not_found`, `retryable`, `blocked` added to possible statuses.
  `new_targets` now has a default (empty list) so callers don't need to pass it.
- `save_raw` now receives `ext` from `tool.raw_ext`.

## Design decisions

**`process` on `FetchTool`, not a separate registry.** Keeps fetch + process paired
at the definition site. Adding a new tool means one entry in `FETCH_TOOLS` with both
functions — no risk of mismatched registries.

**Sync `siren_process`, async `llm_summarize`.** The pipeline uses `inspect.isawaitable`
to handle both. No need to wrap the sync formatter in a coroutine.

**`FetchNotFoundError` for invalid SIREN format.** Could have raised `ValueError`, but
`FetchNotFoundError` keeps the pipeline's error handling uniform — invalid input and
truly missing company both result in `not_found` + skip.

## Next session

- Smoke-test `siren` tool end-to-end with a real SIREN number via `anpe add_target`.
- Prompt tuning for `new_targets` remains the main open item (see previous log).
