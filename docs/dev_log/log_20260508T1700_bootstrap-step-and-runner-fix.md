# Bootstrap engine step + runner fix — 2026-05-08

## What was done

### Bootstrap as an engine step

Converted `anpe bootstrap run` into a proper engine step so it shares the same
scan/put/run pipeline as the rest of the enrichment loop.

**`anpe/bootstrap/search.py`**

- Moved `cache_dir` out of `fetch_pair()`'s signature — callers no longer
  manage the cache path. Hardcoded as `_CACHE_DIR = Path("cache_data") /
  "bootstrap_cache"` inside the module.

**`anpe/bootstrap/pipeline.py`**

- `run()` no longer takes `output_path` or `cache_dir`. It returns
  `list[dict[str, Any]]` (rows) instead of writing the CSV itself.
- Added `rows_to_csv_bytes(rows)` — serializes rows to UTF-8 CSV bytes for
  the vault.

**`anpe/engine/steps/bootstrap.py`** (new)

- `BootstrapStep.scan()` — reads `user_vault/user_profile.yaml`, hashes its
  contents (SHA-256, first 16 hex chars), emits one `Candidate` with
  `profile_hash` in args. If the yaml is unchanged, the uid is unchanged and
  `put` is a no-op. Edit the yaml → new hash → new uid → fresh run scheduled.
  `node_id` is the fixed sentinel `"_bootstrap"` (bootstrap is not per-company).
- `BootstrapStep.work()` — delegates to `pipeline.run()`, serializes to CSV
  bytes, saves to vault at `_bootstrap/listing/{profile_hash}_company_listing.csv`.
  Returns `{"listing_uri": ..., "count": ...}`.
- `--refresh` flag on `scan` and `step` commands passes through to
  `fetch_pair()` to invalidate the API page cache.

**`anpe/cli.py`**

- `BootstrapStep` added to `_make_steps()` and `_KNOWN_STEPS`.
- `--refresh` flag added to `anpe scan` and `anpe step`.
- `_versions` dicts in `put` and `step` updated to include bootstrap.
- `anpe bootstrap run` group removed entirely.

Usage:
```bash
anpe step bootstrap           # hash profile, put if new, run
anpe step bootstrap --refresh # same but invalidate SIRENE API cache
anpe scan bootstrap | anpe put && anpe run --step=bootstrap
```

### Runner bug fix: error_retry infinite loop

**Problem:** A work function raising `RuntimeError` gets marked `error_retry`
and stays in the queue. The worker loops back, claims the same item, fails
again, forever. `test_runner_retryable_error` hung indefinitely.

**Fix:** The runner now tracks attempted uids in `self._attempted` (a set
shared across workers via the lock). Before each `claim()`, the current set is
passed as `skip_uids`. `Queue.claim()` excludes those uids from its SQL query.

`error_retry` is a between-sessions signal: "try again next `anpe run`." Within
a session, each uid is attempted at most once.

`Queue.claim()` now accepts `skip_uids: set[str] | None`. When non-empty, it
injects a `NOT IN (...)` clause. The no-skip path keeps the original query
(no overhead for the common case).

Updated `docs/specs/13_data_engine.md` to document this invariant.

## Status

- All 12 runner tests pass.
- All 8 bootstrap filter tests pass.
- `test_cli_eval.py` has pre-existing failures (unrelated — `_USER_DATA_DIR`
  attribute was removed from `anpe.profile` in a previous session; those tests
  need their fixture updated).

## Next

- Fix `test_cli_eval.py` fixture to patch `USER_DATA_DIR` from `anpe.config`
  instead of the old `_USER_DATA_DIR` from `anpe.profile`.
- Decide where `company_listing.csv` is read from now that it lives in the
  vault — `anpe prospect seed` currently reads from `USER_DATA_DIR /
  "company_listing.csv"`.
