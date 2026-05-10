# Drop pydantic-ai dependency

Date: 2026-05-10

## What changed

Removed pydantic-ai from the codebase entirely. The previous session migrated LLM
steps (summarize, eval) to the `mistralai` SDK directly; this session finishes the job.

### Changes

- `pyproject.toml` — removed `pydantic-ai>=1.88.0`; added explicit `click` and `rich`
  deps (they were previously pulled in transitively via pydantic-ai's dependency tree)
- `anpe/tools/naf.py` — removed `from pydantic_ai import Agent`; dissolved
  `register_naf_tools(agent: Agent)` into two plain top-level functions `naf_lookup`
  and `naf_search` (the wrapper was dead code — no caller since `anpe/agent.py` was removed)
- `scripts/eval_summarize.py` — replaced `Agent` / `MistralModel` / `MistralProvider`
  with direct `mistral_run()` calls from `anpe.clients.mistral`

## Status

81/81 tests pass.
