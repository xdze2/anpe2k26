# Step 5: FetchSirenStep port + run_step fix + Step Protocol

Date: 2026-05-11

## What was done

### Step 5 — `FetchSirenStep` port

Rewrote `anpe/steps/fetch_siren_step.py`:

- Removed all `Queue` usage.
- `scan(vault, overwrite=False, **_)`: reads `listing.jsonl` directly from
  `vault.root`; for each row yields `Candidate(skip=True)` when output already
  exists and `overwrite=False`, otherwise `Candidate(skip=False)`.
  All candidates are always yielded — the caller decides what to do with skipped ones.
- `work(args, vault, log)`: calls `self._fetch(siren)` (a `SirenClient` instance),
  writes to `vault.output_uri(node_id, self.name)`. Made sync (was `async`).
- `__init__` builds a `SirenClient(min_interval_s=1.0)` — rate limiting lives in
  the client, not the engine. `SirenClient` is a callable class that tracks
  `_last_call` with `time.monotonic()` and sleeps for the remaining interval.
  `_last_call` is updated in a `finally` block so it's set even on network error.

Wired up `anpe fetch_siren [--do-max N] [--overwrite]` in `cli.py`.

### `run_step` fix — `do_max` must not count skipped candidates

Bug: `islice(candidates, do_max)` was applied to the raw generator, so a
`skip=True` candidate consumed a `do_max` slot. Running `--do-max 2` after one
node was already fetched would fetch only 1 new node instead of 2.

Fix: eagerly collect all candidates into a list, count skips upfront, then build
a separate iterator of non-skipped candidates and apply `islice` to that.

```python
all_candidates = list(step.scan(vault, **flags))
skipped = sum(1 for c in all_candidates if c.skip)
to_run = (c for c in all_candidates if not c.skip)
if do_max is not None:
    to_run = itertools.islice(to_run, do_max)
```

Trade-off: all candidates are loaded into memory before work starts. Fine for
current listing sizes; worth noting for future very large scans.

### `Step` Protocol in `types.py`

Added `Step(Protocol)` with `@runtime_checkable` and a docstring that documents
the scan/work contract:

- `scan()` yields ALL candidates, including already-done ones with `skip=True`.
- `do_max` is applied only to non-skipped candidates by `run_step`.
- `work()` raises `FatalError` (permanent) or `RetryableError` (transient);
  other exceptions propagate and abort the run.

## Current state

Steps 1–5 done. 15 tests pass (fetch_siren + run_step + bootstrap).
Pre-existing failures in `test_engine_runner.py` / `test_engine_vault.py` unchanged.

## Next

Step 6: port `FetchDDGStep`.
