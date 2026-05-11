# Steps 6-7: FetchDdgStep and SummarizeDdgStep port

Date: 2026-05-11

## What was done

### Step 6 — `FetchDdgStep` port

Rewrote `anpe/steps/fetch_ddg_step.py`:

- Removed all `Queue` usage.
- `scan(vault, overwrite=False, **_)`: globs `nodes/*/fetch_siren_*.json` to find
  nodes with siren data. For each, yields `Candidate(skip=True)` when DDG output
  already exists and `overwrite=False`, otherwise `Candidate(skip=False)`.
- `work(args, vault, log)`: calls `self._fetch(target)` (a `DdgClient` instance),
  writes to `vault.output_uri(node_id, self.name)`. Sync (was `async`).
- `__init__` builds a `DdgClient(min_interval_s=2.0)`.

`_ddg_target()` moved from the old step into the new one unchanged.

### `DdgClient` in `anpe/clients/ddg.py`

Replaced bare `ddg_search()` function with a `DdgClient` callable class — same
pattern as `SirenClient`:

- `_last_call` updated in a `finally` block.
- Maps DDG exceptions to `FetchRetryableError` (rate limit, network), `FetchBlockedError`
  (Cloudflare/CAPTCHA), `FetchNotFoundError` (empty results).

### Step 7 — `SummarizeDdgStep` port

Rewrote `anpe/steps/summarize_ddg_step.py`:

- Removed all `Queue` usage.
- `scan(vault, overwrite=False, **_)`: globs `nodes/*/fetch_ddg_*.json`. Yields
  candidates; `skip=True` when summary output already exists.
- `work(args, vault, log)`: raises `FatalError` if siren data is missing (a node
  can have DDG output but no siren data if files were manually deleted). Calls
  `asyncio.run(ddg_summarize(...))` to bridge the async LLM client into the sync
  `run_step` engine.
- `_fmt_company_profile()` copied from old step unchanged.

Wired up `anpe fetch_ddg [--do-max N] [--overwrite]` and
`anpe summarize_ddg [--do-max N] [--overwrite]` in `cli.py`.

Verified end-to-end: `anpe summarize_ddg --do-max 1` reaches the Mistral API call
and fails with 401 Unauthorized (no key configured) — correct behaviour.

## Current state

Steps 1–7 done. 29 tests pass across all ported steps.
Pre-existing failures in `test_engine_runner.py` / `test_engine_steps.py` / `test_engine_vault.py` unchanged (deleted in step 11).

## Next

Step 8: port `EvalStep`.
