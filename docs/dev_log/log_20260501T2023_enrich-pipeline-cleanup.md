# 2026-05-01 — Enrich pipeline cleanup

## What changed

### `siren_process` is now async

The `process` field on `FetchTool` was typed as `EnrichResult | Awaitable[EnrichResult]`
to accommodate one sync (`siren_process`) and one async (`llm_summarize`) implementation.
This forced `_run_process` to use `inspect.isawaitable` to decide whether to await the result.

`siren_process` does no I/O so making it `async` is trivial. All `process` functions are
now coroutines, `FetchTool.process` is typed as `Awaitable[EnrichResult]`, and `_run_process`
does a plain `await tool.process(...)`. The `inspect` import is gone.

### Dead guard removed in `enrich_step`

`FETCH_TOOLS[entry.tool].raw_ext if entry.tool in FETCH_TOOLS else "txt"` — the guard
was unreachable: `_fetch` already returns a fetch_error and early-returns if the tool is
unknown. Simplified to `FETCH_TOOLS[entry.tool].raw_ext`.

## Design discussion: async and parallelism

Reviewed whether the fetch tools should be async in preparation for parallelizing across
100 companies. Conclusion: **defer until there's an actual perf problem.**

The shape of the solution when needed:
- `siren_fetch` → rewrite with `httpx.AsyncClient` + `await`
- `ddg_search` → wrap with `asyncio.to_thread` (no async API in the `ddgs` library)
- `enrich_batch` → `asyncio.gather` over nodes with a `Semaphore` to cap concurrent LLM calls

Key insight: `asyncio.gather` gives concurrency but not parallelism — a blocking
`httpx.get(...)` inside a coroutine freezes the entire event loop, defeating the gather.
Truly non-blocking requires either an async HTTP client or `to_thread`.

For now: one node at a time, keep the code minimal.

## Next session

- Smoke-test `siren` tool end-to-end with a real SIREN number via `anpe add_target`
- Prompt tuning for `new_targets` (carry-over from previous session)
- Extract `EnrichResult`/`FetchTarget` to `types.py` (low priority, do when adding a third tool)
