# `anpe jobs` + per-run step logging — 2026-05-08

## What was done

### `anpe jobs` — queue inspection command

Two subcommands to inspect the engine queue without touching the DB directly.

**`anpe jobs status [--step=...]`**

Rich table showing each step's item counts by latest event state
(pending / retry / claimed / done / abort). Backed by `Queue.counts()`, a
single SQL query grouping by `(step, event)` over each item's latest event row.

**`anpe jobs history <node_id> [--step=...]`**

Chronological list of all queue events for a node. Shows timestamp, event
type, step, uid prefix, and inline detail (args on `put`, outputs on `done`,
error message on failures, worker id on `claimed`). Backed by
`Queue.node_history()`.

Both commands filter with `--step` to narrow to one step.

The command group is named `jobs` rather than `queue` — `queue` is an
implementation detail, `jobs` is what the user cares about.

**Note on `_bootstrap` as a node_id:** bootstrap is not per-company, so it
uses the sentinel `_bootstrap` as its `node_id`. The underscore prefix
distinguishes process-level steps from company nodes (real node ids never
start with `_`). Slightly off semantically but pragmatic — the queue, vault,
and history queries all work unchanged. Documented in `docs/specs/13_data_engine.md`.

### Per-run step logging

Each `work()` call now receives a `log: Callable[[str], None]` argument.
The runner creates a `StepLogger` per item that buffers timestamped lines
and flushes to `user_vault/{node_id}/{step}/{uid[:8]}.log` when the run
finishes — whether it succeeded or errored.

Steps call `log()` at key points: inputs received, external calls made,
results, errors. Nothing goes to stdout. The file is there when you need it.

**Design choice — no `logging` module:** stdlib `logging` is awkward here
because it uses a global handler hierarchy that fights per-item file routing
under concurrent workers. A plain callable sink is simpler and fits the
existing design (no global state, no configuration, no cross-worker
contamination).

**No log levels:** since the output is a file nobody reads unless debugging,
everything is written at a single flat "debug" level. A timestamp prefix per
line is enough to correlate with queue event timestamps.

`StepLogger` lives in `anpe/engine/logger.py`. `Step` protocol updated in
`base.py`. All four step `work()` methods updated. Test stubs in
`test_engine_runner.py` updated to match the new signature.

## Next

- Fix pre-existing `test_engine_steps.py` failures (`Path` not imported in
  `node_dir.py:432` — `NameError` in `get_latest_eval_result()`).
- Decide where `anpe prospect seed` reads `company_listing.csv` from now
  that bootstrap writes it to the vault.
