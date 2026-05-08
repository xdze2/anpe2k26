# Scan suppression + cleanup plan — 2026-05-08

## What was done

### `scan` suppression for bootstrap

`BootstrapStep.scan()` now suppresses the candidate when a `done` event already
exists for the current profile hash. Previously it always emitted, so
`anpe scan bootstrap` would show a candidate even when the run was already
complete.

**`anpe/engine/queue.py`** — new `is_done(step, version, args) -> bool` helper:
single-row lookup on the content-addressed uid, no full history load needed.

**`anpe/engine/steps/bootstrap.py`** — `scan()` calls `queue.is_done()` and
returns `[]` when already done. `refresh=True` bypasses the check. Importantly,
`refresh` is removed from `args` (hardcoded to `False`) so the uid is stable
regardless of how scan was called — `is_done()` matches correctly in all cases.

**`anpe/cli.py`** — `cmd_step` passes `force=True` to `queue.put()` when
`--refresh` is set, so the duplicate insert goes through despite the existing
done event.

### CLI ergonomics: two-level interface

Confirmed design: `--refresh` lives on both `scan` and `step` as an intent flag.
The everyday interface is `anpe step bootstrap [--refresh]`; the pipe interface
(`anpe scan ... | anpe put [--force] | anpe run`) is for inspection and scripting.
Flags defined once on `scan`, forwarded transparently by `step`.

## Status

- 96 tests pass, 20 errors (all pre-existing, all in old-pipeline tests)
- Engine tests: 37/37 pass

## Next

**Goal: delete all old pipeline code and have a single clean engine.**

### 1 — Fix pre-existing test errors (unblock the suite)

All 20 errors share the same root cause: test fixtures monkeypatch
`_USER_DATA_DIR` on `anpe.profile` but the attribute is now named `USER_DATA_DIR`
(exported from `anpe.config`). Fix: update fixtures to patch `anpe.config.USER_DATA_DIR`.

Files: `tests/test_profile.py`, `tests/test_cli_eval.py`,
`tests/test_eval_pipeline.py`, `tests/test_pipeline_eval_wiring.py`.

### 2 — Port remaining steps to the engine + fix `scan` suppression

Each step needs the same `is_done` suppression fix as bootstrap:

- **`summarize_ddg`** — `scan()` should skip `(node, raw_uri)` pairs that
  already have a done event at the current version.
- **`eval`** — same for `(node, sum_uri, profile_uri)` triples.
- **`fetch_ddg`** — already pull-sourced from targets; revisit once the others
  are done.

### 3 — Delete old pipeline code

Once the engine steps are correct and tests pass, remove:
- `anpe/prospect/pipeline.py`
- `anpe/prospect/eval_pipeline.py`
- `anpe/prospect/eval.py` (logic already ported to `EvalStep`)
- `anpe/prospect/summarize.py`
- `anpe/prospect/fetch/` (logic already in `FetchDdgStep`)
- Old CLI commands: `prospect resummarize`, `prospect reeval`, `anpe run` (old path)
- Associated tests that test the deleted code

### 4 — Fix `prospect seed`

`prospect seed` still reads `user_data/company_listing.csv`. After bootstrap
the listing lives in the vault. Seed needs to read the latest bootstrap listing
URI from the queue and load it from the vault instead.
