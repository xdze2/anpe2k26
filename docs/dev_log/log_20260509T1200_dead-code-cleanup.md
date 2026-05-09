# Dead code cleanup — 2026-05-09

## Context

The data engine (spec 13) replaced the old `prospect/pipeline.py` approach.
Steps now use the queue+vault model. A review of the codebase identified three
categories of dead code: superseded pipeline files, orphaned CLI commands, and
write methods on `NodeDir` that the engine no longer calls.

## What was removed

### Deleted files

- **`anpe/prospect/pipeline.py`** — `enrich_step()` / `run_batch()` replaced by
  engine steps. The only surviving export (`StepLog`) was used by a dead helper
  in `cli.py`.
- **`anpe/prospect/eval_pipeline.py`** — `eval_step()` / `run_eval_batch()`
  replaced by `engine/steps/eval.py`. Never imported outside its own test.
- **`anpe/prospect/fetch/siren.py`** — 8-line dead re-export; nothing imported
  it; engine imports directly from `anpe.clients.siren`.

### Deleted test files

- `tests/test_pipeline_eval_wiring.py` — tested `enrich_step()`
- `tests/test_eval_pipeline.py` — tested `eval_pipeline.py`
- `tests/test_node_dir_eval.py` — tested the eval queue write methods on
  `NodeDir`, which are now removed
- `tests/test_cli_eval.py` — tested the `prospect reeval` CLI command, which
  is now removed

### cli.py

- Removed `TYPE_CHECKING` guard and `StepLog` import from `prospect.pipeline`.
- Removed `_print_step_log()` (never called).
- Removed `prospect seed` — seeding is now done by the `bootstrap` step.
- Removed `prospect add_target` — targets are no longer written to `fetch.jsonl`.
- Removed `prospect resummarize` — wrote `resummarize` events to old `fetch.jsonl`
  which the engine never reads.
- Removed `prospect reeval` — enqueued into `eval_queue.jsonl`, not into
  `queue.db`; the engine ignores that file.

### node_dir.py

Removed all write methods — the engine no longer writes to the old node layout:

- `_append_fetch_event`, `append_target`, `pop_pending`
- `mark_fetch_done`, `mark_fetch_error`
- `mark_summarize_done`, `mark_summarize_error`, `mark_resummarize`
- `get_stale_summarize_uids`
- `save_raw`, `save_summarize_result`
- `_append_eval_event`, `append_eval_put`, `mark_eval_done`, `mark_eval_error`,
  `mark_eval_discarded`, `pop_eval_pending`, `save_eval_result`, `is_eval_stale`

Kept: all read-only methods (`get_fetch_history`, `get_latest_summary`,
`get_siren_meta`, `get_latest_eval_result`, etc.) because the remaining `prospect`
display commands (`list`, `status`, `show`, `map`) still read the old on-disk
data. Kept `append_review` / `get_latest_review` — the review UI still writes
here. Removed `secrets` import (was only used by the deleted `_uid()` helper).

Section headers in the docstring updated to reflect read-only status.

### prospect/seed.py

Removed `seed_from_listing`, `_read_unique_rows`, the `NodeDir` import, and the
`csv` import. These were only called from `prospect seed` (now removed). Kept
`slugify` and `node_id_for` — used by `engine/steps/fetch_siren.py`.

The file is now a pure node-ID utility module; the docstring was updated to
reflect this.

`tests/test_prospect_seed.py` trimmed to the four unit tests for `slugify` and
`node_id_for`; the three `seed_from_listing` integration tests were removed.

## Status

81 tests pass (down from 108 before: 19 tests removed for dead code, 8 tests
removed with the deleted pipeline test files).

## What remains of the old pipeline

`node_dir.py` is now read-only from the engine's perspective. The display
commands still work as long as old `fetch.jsonl` files exist on disk. Once those
nodes are migrated to the engine (or discarded), `NodeDir` can be retired
entirely. The `prospect review` command is the only one that still writes to
`node_dir` — it is the candidate for the upcoming `node_view` / `node_review`
rewrite.
