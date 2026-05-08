# fetch_ddg scan from bootstrap listing — 2026-05-08

## What was done

### Bootstrap output: CSV → JSONL

Bootstrap step now writes `_bootstrap/bootstrap/{ts}_listing.jsonl` (one JSON
object per company per line) instead of a CSV. `rows_to_jsonl_bytes()` added to
`bootstrap/pipeline.py`. `rows_to_csv_bytes()` kept for the old `anpe prospect`
CLI path.

`BootstrapStep.version` bumped to `v2`.

### Vault: store() replaces save()

`Vault.save(uri, data)` removed. Replaced by `Vault.store(node_id, step, slug,
ext, data) -> str` which builds the URI internally as
`{node_id}/{step}/{ts}_{slug}.{ext}` and returns it opaque to the caller.

Callers never construct URIs — they pass metadata and get back a token. This
keeps the vault backend-agnostic (filesystem today, could be SQLite or S3
tomorrow).

`profile_hash` in bootstrap's args is an *input signal* for `put` idempotency
(it participates in the content-addressed uid). It is not embedded in the
artifact path — that's the vault's job.

### fetch_ddg.scan() reads bootstrap listing

`FetchDdgStep.scan(count=N)` now has two candidate sources:
- `_scan_listing(count)` — new companies from the bootstrap listing, capped at N
- `_scan_followups()` — existing `fetch.jsonl` pending DDG entries (uncapped)

`work()` calls `vault.store()` and no longer constructs URIs itself. The vault
creates the node dir implicitly via `path.parent.mkdir()`.

## Known issue / next session

`_scan_listing()` currently bypasses the vault abstraction by globbing
`USER_VAULT_DIR` directly for `_bootstrap/bootstrap/*_listing.jsonl`. This is
wrong: scan should not know what vault paths look like internally.

**Fix:** `fetch_ddg.scan()` should query the Queue for the latest `done` event
on the `bootstrap` step, extract `outputs["listing_uri"]`, then call
`vault.load(listing_uri)` to get the JSONL bytes. The vault is opaque; the
queue's event log is the right dependency channel between steps.

Bootstrap's profile path as a hardcoded constant input is fine — it's the
pipeline entry point with no upstream queue to read from.
