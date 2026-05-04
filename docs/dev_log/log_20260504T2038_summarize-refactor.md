# 2026-05-04 — Summarize step refactor

## What was done

A series of small refactors to clarify ownership and naming in the enrichment pipeline.

### Output metadata moved out of `fetch.jsonl`

`fetch.jsonl` now carries only control-flow fields (`uid`, `result_file`, `ts`).
`model`, `prompt_version`, and `status` were removed from `summarize_done` events.
`not_relevant` gets its own event (`summarize_not_relevant`) instead of a status field.

`sum_*.json` now owns the full step signature:
- `raw_file` — pointer to the input that produced this summary
- `summarize_version` — hash of system prompt + model name (bumps on either change)
- `model` — model name used
- `prompt` — full prompt text sent to the LLM (system + user)

This makes staleness detection straightforward: scan `sum_*.json` files, compare `summarize_version` to the current constant.

### `SUMMARIZE_VERSION` replaces `PROMPT_VERSION`

The hash now covers system prompt + model name (`_MODEL_NAME`), so a model bump
automatically invalidates existing summaries. A single `_MODEL_NAME` constant
is shared between the hash and the `MistralModel()` instantiation.

### `FetchTarget` and `SummarizeResult` moved to `types.py`

New `anpe/prospect/types.py` holds the shared data models. `siren.py` no longer
imports from `summarize.py`. `SummarizeResult` gained `model` and `prompt` fields
so the pipeline doesn't need to pass `settings.mistral_model` — each summarize
function owns its own metadata.

### `capture_prompt` flag removed

Each summarize function now returns `prompt` and `version` in `SummarizeResult`.
The pipeline saves `prompt_*.txt` alongside `sum_*.json` unconditionally.
`FetchTool.capture_prompt` and `NodeDir.prompt_file_path()` are gone.

### Renames

- `EnrichResult` → `SummarizeResult`
- `llm_summarize` → `ddg_summarize`
- `siren_process` → `siren_summarize`
- `FetchTool.process` → `FetchTool.summarize`
- `_all_node_ids_by_ctime` moved from `pipeline.py` to `node_dir.py` (public)

## Next

- Implement `anpe prospect resummarize` — scan nodes for stale `summarize_version`, re-queue them
