# Rate limiter refactor + client singletons

Date: 2026-05-11

## What was done

### `RateLimiter` as a callable wrapper

`anpe/clients/rate_limiter.py` rewritten: `RateLimiter` now wraps a callable
and enforces the interval in `__call__` (wait → delegate → finally: mark).
Callers no longer need to manage `_last_call` or call `wait()`/`mark()`
manually.

### Module-level singletons

Each client is now a plain function + a module-level `RateLimiter` singleton:

- `anpe/clients/siren.py`: `_siren_fetch()` + `siren_client = RateLimiter(_siren_fetch, 1.0)`
- `anpe/clients/ddg.py`: `_ddg_search()` + `ddg_client = RateLimiter(_ddg_search, 2.0)`
- `anpe/clients/mistral.py`: `_mistral_complete()` + `mistral_complete = RateLimiter(_mistral_complete, 1.0)`

Rate limit is now enforced across all Step instances, not per-instance.

### Steps simplified

`FetchSirenStep` and `FetchDdgStep` no longer have `__init__` — they import
the singleton directly. `SirenClient` and `DdgClient` classes are gone.

### Mistral client simplified

Retry logic dropped. `mistral_run` is now a thin typed adapter:
builds messages → calls `mistral_complete` → validates JSON into the output type.
`LLMCapacityError` and `LLMCreditsError` still raised from `_mistral_complete`
for unretryable errors (402, 3505).

### `eval_fn` and `summarize_fn` made sync

`llm_eval` and `ddg_summarize` were still `async`/using `asyncio.run()` — both
converted to plain sync functions, matching the sync `run_step` engine.

### Deprecated test files deleted

`test_engine_runner.py`, `test_engine_queue.py`, `test_engine_steps.py`,
`test_engine_vault.py` removed (code they tested is deprecated).

## Current state

55 tests pass. Steps 1–7 done and clean.

## Next

Step 8: port `EvalStep`.
