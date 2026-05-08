# `scan(queue)` + step registry — 2026-05-08

## What was done

### `scan(queue, ...)` — queue as explicit environment arg

`Step.scan()` now takes `queue: Queue` as its first positional argument.
Rationale: `queue` and `vault` are the step's environment — stateful services it
reads/writes. Making `queue` explicit in `scan()` keeps the dependency visible at
the call site and avoids hidden global state. `log` stays in `work()` only
(it's a per-item sink, meaningless before an item is claimed).

**`anpe/engine/steps/base.py`** — `Step` protocol updated: `scan(self, queue: Queue, **filter_flags)`.

**All four step classes** — `scan()` signature updated to accept `queue` as first arg.
Three of them (`bootstrap`, `summarize_ddg`, `eval`) ignore it for now; it's there
for consistency and future use.

**`anpe/engine/steps/fetch_ddg.py`** — `_scan_listing` now uses the queue instead
of globbing the vault directory. It calls `_latest_bootstrap_listing_uri(queue)`,
which walks `queue.node_history("_bootstrap", step="bootstrap")` in reverse and
returns the `listing_uri` from the last `done` event's outputs. This guarantees
we only read a listing from a successfully completed bootstrap run — the old glob
had no way to distinguish a partial/failed run from a finished one.

**`anpe/cli.py`** — both `cmd_scan` and `cmd_step` open a `Queue` before calling
`scan()`. In `cmd_step` the queue was already created later in the function; it
now moves up above the `scan()` call.

**`anpe/node_dir.py`** — fixed pre-existing `NameError`: `Path` was used in
`get_latest_eval_result()` but never imported.

### Step registry

**`anpe/engine/registry.py`** (new) — `STEPS: dict[str, Step]` is the single
place where step classes are imported and instantiated. `_load()` builds the dict;
the module-level `STEPS` singleton is imported by the CLI.

Adding a new step now means: create the step module, add one line in `registry.py`.
Nothing else.

**`anpe/cli.py`** — `_make_steps()` removed. `_KNOWN_STEPS` is now derived from
`list(_STEPS)` so it stays in sync automatically. The three duplicated `_versions`
dicts in `cmd_put`, `cmd_step` are gone — version is read from `_STEPS[name].version`
directly. `cmd_run` and `cmd_step` build the runner with `list(_STEPS.values())`.

### `description` class attribute + `anpe steps` command

Each step class now has a `description: str` class attribute (one line, added to
the `Step` protocol). It's shown in the new `anpe steps` command:

```
 bootstrap      v2      Hash user_profile.yaml and produce a company listing JSONL in the vault.
 fetch_ddg      v1      Fetch raw DDG search results for companies from the bootstrap listing or follow-up targets.
 summarize_ddg  54e33d  Summarize raw DDG fetch results with an LLM and extract follow-up targets.
 eval           d83975  Score each summarized company against the user profile and assign a fit level.
```

`anpe steps` (plural) lists registered steps. `anpe step <name>` (singular) runs
one — no naming conflict.

### Test updates

**`tests/test_engine_steps.py`** — `_make_queue(tmp_path)` helper creates a
scratch `Queue` in `tmp_path`. Each test class stores `self.queue` in its
`autouse` fixture and passes it to every `scan()` call.

Two new tests for the listing-via-queue path in `TestFetchDdgStepScan`:
- `test_listing_from_queue_emits_candidates` — puts a completed bootstrap `done`
  event with a known `listing_uri`, writes the JSONL file, asserts candidates are
  emitted with the correct target and URI.
- `test_no_listing_when_bootstrap_not_done` — bootstrap is `put` but not `done`,
  asserts no candidates.

**`tests/test_engine_runner.py`** — `patch_nodes` autouse fixture now also patches
`anpe.engine.queue.QUEUE_DB` so `cmd_scan` CLI tests don't try to write to the
real `user_vault/`.

## Status

- 37 engine tests pass (25 step tests + 12 runner tests).

## Next

- Fix pre-existing `test_cli_eval.py` fixture (`_USER_DATA_DIR` → `USER_DATA_DIR`
  from `anpe.config`).
- Fix pre-existing `test_eval_pipeline.py` / `test_profile.py` `AttributeError`
  errors (unrelated to this session).
- Decide where `anpe prospect seed` reads `company_listing.csv` from now that
  bootstrap writes to the vault.
