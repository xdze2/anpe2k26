# Stale claim recovery in `anpe step` — 2026-05-08

## What was done

### Bug: `anpe step` skipped the runner when nothing new was queued

**Problem:** killing a worker mid-run leaves the queue item stuck at `claimed`.
On the next `anpe step`, `scan` finds the same candidate (same profile hash →
same uid), `put` is a no-op ("already present"), `queued == 0`, and `cmd_step`
returned early — before ever creating the runner. The stale-claim sweep lives
inside the runner's worker loop, so it never ran. The item stayed stuck forever.

**Root cause:** a gap between the spec and the implementation. The spec
(`docs/specs/13_data_engine.md`) says the runner's `_sweep_stale` recovers
crashed workers. But `anpe step` had an early-return guard (`if queued == 0:
return`) that prevented the runner from starting when all candidates were
already present in the queue.

**Fix:** one-line change in `cmd_step` (`anpe/cli.py`):

```python
# before
if queued == 0:
    queue.close()
    return

# after
if queued == 0 and not queue.stale_claims(step_name):
    queue.close()
    return
```

Now `anpe step` only skips the runner if there is nothing queued *and* no stale
claims. If a killed worker left a `claimed` item older than `CLAIM_TIMEOUT_S`
(300 s), the runner starts, the sweep fires on the first worker iteration,
inserts `error_retry`, and the item is claimed and completed normally.

The same path works for `anpe run` — it always starts the runner, so the sweep
was already effective there.

### Design note

The two recovery mechanisms in the spec are:

1. **Stale claim timeout** — runner sweeps on each poll cycle; items claimed
   > 5 min ago get `error_retry`. Handles mid-run crashes.
2. **Within-session skip set** — `_attempted` prevents infinite retry loops
   for items that error on every attempt.

These two concerns are independent. This fix ensures mechanism 1 is reachable
from `anpe step`, not just `anpe run`.

Multi-worker support (concurrent workers racing to claim) was considered but
deferred — overkill for current usage. The content-addressed uid and
SQLite-serialised writes already make it safe if it becomes needed.

## Status

- `anpe step bootstrap` now recovers the stuck claim, runs the job, exits clean.
- No test changes needed — runner tests already cover stale-claim recovery via
  `_sweep_stale`.

## Next

- Fix pre-existing `test_engine_steps.py` failures (`Path` not imported in
  `node_dir.py` — `NameError` in `get_latest_eval_result()`).
- Decide where `anpe prospect seed` reads `company_listing.csv` from now that
  bootstrap writes it to the vault.
