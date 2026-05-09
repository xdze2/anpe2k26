# EvalStep rewrite — queue-sourced scan + vault output — 2026-05-09

## Problem

`EvalStep.scan()` was reading from the old-pipeline filesystem layout:
it walked `user_data/nodes/<id>/summarize/` looking for summary files, and
checked `eval_results/*.json` on disk to decide whether an eval was already
done. This bypassed the queue entirely and coupled the step to `NodeDir` /
`NODES_DIR` — the old system we are phasing out.

`EvalStep.work()` returned the result dict to the runner but never wrote
anything to the vault. The score was stored only in the queue's `done` event
`outputs` column — invisible as a file, the same bug that was fixed for
`summarize_ddg` in the previous session.

## Fix

### scan() — source from queue

Rewired to iterate `queue.done_events("summarize_ddg")` and read `summary_uri`
from each done event's outputs. Dedup is `queue.is_done(self.name,
self.version, args)` — the same content-addressed pattern every other step uses.
Profile is `"user_preference.md"` — a vault-relative URI, loaded in `work()`
via `vault.load()`. No filesystem walk, no `NodeDir`, no `active_profile_file`.

Dropped for now (TODO comments left in code):
- `min_score` filter — needs reading prior eval done events
- `exclude_reaction` filter — needs reactions stored in the queue
- `naf` context field — needs a source that isn't `NodeDir`

### work() — save to vault

Serialises the result payload as JSON and saves it via `vault.store()` before
returning, mirroring the fix applied to `summarize_ddg`. Saved file includes
score, fit, dealbreakers, uncertainty, plus back-references to `summary_uri`
and `profile_uri` for traceability. `eval_uri` is echoed through the returned
outputs dict.

### Version bump

`EvalStep.version` changed from `EVAL_VERSION` to `EVAL_VERSION + ".2"` to
invalidate existing done events (which had no vault file) and trigger re-runs.

## Changes

**`anpe/engine/steps/eval.py`**
- `scan()`: rewritten — queue-sourced, vault-aware, no NodeDir.
- `work()`: add `vault.store()` call, include back-refs in payload, return
  `eval_uri` in outputs dict.
- `version`: append `.2` suffix.
- Removed imports: `NodeDir`, `NODES_DIR`, `active_profile_file`, `Path`.
- Removed helpers: `_has_eval_for`, `_score_gte`.

**`tests/test_engine_steps.py::TestEvalStepScan`**
- Fully rewritten: seeds `summarize_ddg` done events and writes
  `user_preference.md` directly to vault root. No `NODES_DIR` monkeypatching,
  no old-pipeline node fixture helpers.

**`tests/test_engine_runner.py`**
- Removed stale `anpe.engine.steps.eval.NODES_DIR` monkeypatch from the
  module-level autouse fixture.

## Status

- 108 tests pass.
- Re-ran `anpe step eval` against the 10 existing summarized nodes — all 10
  got eval JSON files written to `user_vault/<node>/eval/`.

## Next

- P1.2: `BootstrapStep.refresh` silent bug (hardcoded `args["refresh"] = False`).
- Future: add `min_score` / `exclude_reaction` filters once those signals live
  in the queue.
