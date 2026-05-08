# Data engine — chunk 4 (Runner + CLI) — 2026-05-08

## What was done

Implemented chunk 4 of the data engine spec (`docs/specs/13_data_engine.md`).

### Runner (`anpe/engine/runner.py`)

Async worker loop: `run_until_empty(step_name, budget)`. Multiple concurrent
workers per step, stale-claim sweep before each claim, `budget` cap. Three
outcome statuses: `done`, `error_retry` (RuntimeError), `error_abort`
(any other exception). Returns a list of `RunResult` dataclasses.

### CLI wiring (`anpe/cli.py`)

Rewrote the CLI file. Changes from previous version:

**Removed:**
- `anpe chat` — dead branch
- `anpe prospect run` — replaced by `anpe run`
- `anpe prospect eval` — replaced by `anpe scan eval | anpe put` + `anpe run`

**Added (top-level engine commands):**
- `anpe scan <step> [--flags]` — lists candidates as JSON, one per line (stdout)
- `anpe put` — reads JSON lines from stdin, enqueues them in the queue
- `anpe run [--step=] [--budget=]` — drains the queue
- `anpe step <step> [--flags] [--budget=]` — scan + put + run in one command

**Kept under `anpe prospect`:** `list`, `show`, `map`, `review`, `status`,
`seed`, `add_target`, `resummarize`, `reeval`.

**Kept as-is:** `anpe profile update`, `anpe bootstrap run`.

### Tests (`tests/test_engine_runner.py`)

12 tests covering:
- Runner: drains queue, retryable error, fatal error, budget cap, empty queue
- `anpe scan`: empty output, JSON-line output with correct fields
- `anpe put`: stdin reading, idempotency
- `anpe scan/run/step --help` smoke tests

Also updated `tests/test_cli_eval.py`: removed the 3 tests for the now-dropped
`anpe prospect eval` command; kept the `reeval` tests.

### Bug fix in `Queue.claim()`

`claim()` was reading `args` from `e.args` (the latest event row). When the
latest event is `error_retry`, that column is NULL — only `put` events carry
args. Fixed by joining back to the original `put` event row, consistent with
how `pending()` and `stale_claims()` already work.

## Status

Tests were running when the session was stopped. Two failures were observed
mid-run before the fix and test adjustments:

1. `test_runner_retryable_error` — caused by the `claim()` bug above (fixed).
2. `test_step_help` — test was checking for `fetch_ddg` in `--help` output,
   but click renders `Choice` args as `STEP` in the metavar. Fixed test to
   check for `STEP` and `--budget` instead.

## Next

- Confirm full test suite passes (`uv run pytest`).
- Debug step by step if anything remains red.
- Consider adding an integration test: `scan | put | run` against a fixture
  node, verify event log state after completion.
