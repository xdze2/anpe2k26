# Clients refactor: ddg and errors move out of prospect

Date: 2026-05-09

## What changed

Two modules were living under `anpe.prospect` but had no logical tie to the
prospect layer — they are generic external-service wrappers. Both were moved to
`anpe.clients`.

### anpe/prospect/fetch/ddg.py → anpe/clients/ddg.py

`ddg_search` is a thin wrapper around the `ddgs` library. It belongs next to
`siren.py` as a client, not inside the prospect fetch sub-package.

`anpe/prospect/registry.py` was the only importer; its import was updated.

### anpe/prospect/errors.py → anpe/clients/errors.py

`FetchNotFoundError`, `FetchRetryableError`, and `FetchBlockedError` are
client-level signals — they describe what an external service returned. They
have nothing to do with the prospect domain.

The correct layering is now explicit:
- **client raises** `FetchNotFoundError` / `FetchRetryableError` / `FetchBlockedError`
- **engine step catches** those and re-raises as `FatalError` / `RetryableError`

Four import sites updated: `clients/ddg.py`, `clients/siren.py`,
`engine/steps/fetch_ddg.py`, `engine/steps/fetch_siren.py`.

## Status

81 tests pass, unchanged.

## What remains

`anpe/engine/steps/summarize_ddg.py` still imports from `anpe.prospect.registry`
and `anpe.prospect.summarize` — noted as next cleanup target.
