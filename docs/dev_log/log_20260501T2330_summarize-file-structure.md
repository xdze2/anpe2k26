# 2026-05-01 — Summarize result files + prompt capture

## What changed

### `summarize.jsonl` dropped — replaced by `summarize/` directory

`summarize.jsonl` was an append-only log with one entry per LLM call. It duplicated
the `summarize_done` status already in `fetch.jsonl`, and mixed the state-machine role
of `fetch.jsonl` with rich output storage.

New layout:

```
summarize/
  sum_<tool>_<target>_<status>_<ts>.json   — one result file per process run
  prompt_<tool>_<target>_<ts>.txt          — LLM prompt (debug, temporary)
```

`fetch.jsonl` `summarize_done` events gain a `result_file` field pointing to the JSON
file — mirroring how `fetch_done` carries `raw_file`. The file name is decorative;
`result_file` in `fetch.jsonl` is the authoritative link.

Re-running `anpe summarize` after a prompt change writes a new file each time —
history is preserved, `fetch.jsonl` always points to the latest.

### `NodeDir` changes (`anpe/node_dir.py`)

- `_summarize_file` removed; `_summarize_dir` added (`summarize/` subdir, created by `init()`).
- `append_summarize_event` → `save_summarize_result`: writes one JSON file, returns filename.
- `prompt_file_path(entry, ts)`: returns the path for a prompt debug file (caller writes it).
- `mark_summarize_done` gains `result_file: str` param, stored in `fetch.jsonl`.

### Prompt capture (`anpe/enrich/summarize.py`, `registry.py`, `pipeline.py`)

`llm_summarize` accepts an optional `prompt_file: Path` — if set, writes the assembled
prompt to disk before the LLM call. No change to the return type or call signature for
callers that don't need it.

`FetchTool` gains `capture_prompt: bool` (default `False`). Set to `True` for `ddg`
(LLM-backed). The pipeline checks the flag: if set, it computes the prompt path via
`node.prompt_file_path` and calls `llm_summarize` directly with it; otherwise it calls
`tool.process` as before. `siren_process` is unaffected — no LLM, no prompt to capture.

## Design decisions

**Side-channel file, not a return value.** Threading `prompt` up through `tool.process`
→ `_run_process` → `save_summarize_result` would require changing every tool's signature
for a temporary debug feature. Instead, `llm_summarize` writes the file itself when
given a path — self-contained, easy to remove later.

**`capture_prompt` flag on `FetchTool`.** Keeps the registry as the single place that
describes what each tool does. The pipeline doesn't need to know which tools use LLM —
it just checks the flag.

**File name is decorative.** `sum_ddg_KAYRO_ok_20260501T204211.json` is readable when
browsing the directory, but the authoritative link is `result_file` in `fetch.jsonl`.
No logic depends on parsing the filename.

## Next

- Remove prompt capture once prompt tuning is done (delete `capture_prompt` flag,
  `prompt_file_path`, and the `if tool.capture_prompt` branch in pipeline).
- Add `status` display from `summarize_done` event to `anpe status` output.
