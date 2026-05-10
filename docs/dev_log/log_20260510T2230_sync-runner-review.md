# SyncRunner + interactive ReviewStep

Date: 2026-05-10

## Problem

`ReviewStep.work` was `async` and routed through the async `Runner` with
`concurrency=4`. This caused two bugs:
- 4 concurrent `questionary.select()` prompts flooded the terminal at once.
- `questionary` internally calls `asyncio.run()`, which raises
  `asyncio.run() cannot be called from a running event loop` inside the
  already-running async runner — every review item was `error_abort`ed.

## What changed

### engine/base.py

`Step` protocol split into a hierarchy:

- `Step` — base protocol: `scan()` + metadata only.
- `AsyncStep(Step)` — adds `async def work(...)`.
- `SyncStep(Step)` — adds `def work(...)`.

### engine/sync_runner.py (new)

Plain serial `for` loop. No asyncio. Calls `step.work()` directly.
Same claim/mark_done/mark_error/stale-sweep logic as `Runner`.

### engine/runner.py

Unchanged behaviour. Now typed against `AsyncStep` instead of `Step`.

### steps/review_step.py

- `work` is now a plain `def` (SyncStep).
- Replaced `input(" > ")` with `questionary.select()` — arrow-key choice
  from `interested / not_interested / more_data / skip`.
- Escape / Ctrl+C / Ctrl+D → `questionary` returns `None` → raises
  `RetryableError("skipped")`: item stays in queue, not marked done.
- `skip` choice → same.

### cli.py

Added `_is_sync(step)` (checks `asyncio.iscoroutinefunction(step.work)`)
and `_split_steps(names)`. Both `cmd_run` and `cmd_step` now route sync
steps to `SyncRunner` and async steps to `Runner`. The two runners run
sequentially within the same CLI invocation.

### queue data repair

32 review items were stuck as `error_abort` from the asyncio crash.
Reset by inserting a new `error_retry` event for each — they are now
pending again.

## Status

84/84 tests pass.
