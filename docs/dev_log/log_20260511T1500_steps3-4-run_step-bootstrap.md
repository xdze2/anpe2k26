# Steps 3 & 4: run_step helper and bootstrap port

Date: 2026-05-11

## What was done

### Step 3 — `engine/run_step.py`

Created `anpe/engine/run_step.py` with two functions:

- `log_appender(vault, node_id)`: context manager that ensures
  `nodes/<node_id>/node.log` (or `node.log` for process-level steps) exists and
  returns an append-only `Log` callable.
- `run_step(step, vault, do_max, **flags) -> (ran, skipped)`: consumes
  `step.scan(vault, **flags)`, optionally sliced by `do_max`, calls `step.work`
  inside `log_appender`, counts ran/skipped. `FatalError` and `RetryableError`
  are caught and logged; other exceptions propagate.

One detail: `log_appender` calls `log_path.touch()` on enter so the log file
always exists after a candidate is processed, even when `work()` emits no log
messages. This makes it easy to check "was this node touched?" by file existence.

5 tests in `tests/test_engine_run_step.py`.

### Step 4 — `BootstrapStep` port

Rewrote `anpe/steps/bootstrap_step.py`:

- Removed all `Queue` / `queue.is_done` usage.
- `scan(vault, overwrite=False, **_)`: returns early if `seed_query.yaml` is
  missing; returns early if `listing.jsonl` exists and `overwrite=False`; otherwise
  yields one process-level `Candidate(node_id=None)`.
- `work(args, vault, log)`: calls `_pipeline_run(profile_path)`, serialises rows
  with `rows_to_jsonl_bytes`, writes directly to `vault.root / "listing.jsonl"`
  (plain overwrite — not content-addressed). Made sync (was `async`).
- Dropped `profile_hash`, `version`, `rate_gate`, `description` — not needed by
  the new loop.

Wired up `anpe bootstrap [--overwrite]` in `cli.py` using `run_step`. Prints
`bootstrap: ran=N skipped=M` on completion.

Also cleaned up the remaining CLI stubs: removed duplicate Python function names
(`cmd_eval` appeared twice), removed unused imports (`asyncio`, `itertools`,
`json`, `sys`, `NodeDir`, rich imports), gave each stub a `NotImplementedError`
body with the step number. `anpe --help` verified working.

5 tests in `tests/test_bootstrap_step.py`.

## Current state

Steps 1–4 done. Full test suite: 87 pass, 7 fail (pre-existing failures in
`test_engine_runner.py` — old engine tests, deleted in step 11).

## Next

Step 5: port `FetchSirenStep`.
