# Vault.write refactor + skipped count fix

Date: 2026-05-11

## What was done

### `Vault.store()` → `Vault.write(uri, data, log=None)`

`store()` was a poor fit for the new architecture: it generated timestamped,
content-addressed URIs internally (`{step}/{node_id}/{ts}_{slug}.{ext}`) with a
`slug` parameter that every caller set to `node_id[:8]` — redundant and
inconsistent with `output_uri()`. It also enforced write-once semantics that
conflict with `--overwrite`.

Replaced with `write(uri, data, log=None)`:
- Caller supplies the URI (typically via `vault.output_uri(node_id, step_name)`
  or a fixed path like `"listing.jsonl"`).
- Overwrites silently — skip logic lives in `scan()`, not here.
- Prints `wrote N bytes → uri` to stdout and, if `log` is provided, also writes
  to the node log. Both outputs in one call, no duplication at call sites.

`bootstrap_step`, `fetch_siren_step`, and `fetch_ddg_step` updated. Remaining
steps left for their respective port steps (5+) since they will be rewritten anyway.

`datetime`/`timezone` imports and `_ts()` helper removed from `vault.py`.

### `Candidate.skip` + `skipped` count fix

`anpe bootstrap` reported `skipped=0` on second run because `scan()` returned
early (yielded nothing) when `listing.jsonl` already existed. `run_step` only
saw zero candidates, so both counters stayed at zero.

Fix: added `skip: bool = False` to `Candidate`. `scan()` now always yields one
candidate when the seed file exists, setting `skip=True` when output already
exists and `overwrite=False`. `run_step` increments `skipped` for these and
does not call `work()`.

Second run now correctly prints `bootstrap: ran=0 skipped=1`.

## Current state

Steps 1–4 done. Vault API simplified. 10 tests pass (bootstrap + run_step).
Pre-existing failures in `test_engine_runner.py` unchanged (deleted in step 11).

## Next

Step 5: port `FetchSirenStep`.
