# Mistral client refactor — drop pydantic-ai for LLM steps (WIP)

Date: 2026-05-09

## What changed

Replaced pydantic-ai's `Agent`/`MistralProvider` with the `mistralai` SDK directly
for the summarize and eval steps. All LLM call logic is now consolidated in
`anpe/clients/mistral.py`.

### Motivation

- pydantic-ai was used only for structured-output parsing — no tools, no multi-turn,
  no agent features. It was adding a layer of abstraction for something that's
  10 lines of `mistralai` SDK + `model.model_validate()`.
- The retry/error handling in `summarize_fn.py` and `eval_fn.py` was duplicated
  identically, with fragile `"429" in str(e)` string matching on wrapped exceptions.
- The 429 from Mistral was being retried even when it was a quota-exhaustion error
  (code 3505, `service_tier_capacity_exceeded`) — unretryable by nature.

### Changes

- Added `mistralai` to deps, removed `pydantic-ai-slim[mistral]`
- `anpe/clients/mistral.py` — new: single `async def mistral_run(output_type, model,
  system, prompt) -> T` with proper error classification:
  - `SDKError.status_code == 402` → `LLMCreditsError` (no credits)
  - `SDKError.status_code == 429` + body contains `3505` → `LLMCapacityError` (quota, no retry)
  - `SDKError.status_code == 429` otherwise → transient rate-limit, retry with backoff
- `anpe/steps/summarize_fn.py` — retry loop and `_agent` removed; calls `mistral_run`
- `anpe/steps/eval_fn.py` — same
- `anpe/steps/summarize_fn.py` system prompt: `new_targets` description changed from
  "list of (tool, target) pairs" to `{"tool": ..., "target": ...}` objects — pydantic-ai
  was injecting its JSON schema; raw JSON mode needs the structure explicit in the prompt
- `tests/test_eval.py` — replaced `_agent.override(model=TestModel(...))` with
  `unittest.mock.patch("anpe.clients.mistral._client")`

## WIP — pydantic-ai not fully removed

`pydantic-ai` is still in deps because the main chat agent (`anpe/agent.py`, `anpe/cli.py`)
uses it for the interactive REPL loop with OpenRouter. Two other files also remain:

- `anpe/tools/naf.py` — `Agent` used only as a type annotation for `register_naf_tools`;
  this is the main chat agent, not a Mistral step
- `scripts/eval_summarize.py` — script using pydantic-ai + MistralProvider directly,
  now stale after the refactor

Full removal of pydantic-ai requires migrating the main chat agent away from it,
which is a separate and larger task.

## Status

81/81 tests pass. `mypy anpe/clients/mistral.py` clean.
