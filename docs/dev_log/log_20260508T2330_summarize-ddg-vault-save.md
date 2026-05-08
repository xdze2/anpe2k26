# summarize_ddg — fix missing vault output — 2026-05-08

## Problem

`SummarizeDdgStep.work()` called the LLM, got a result, and returned a dict —
but never wrote anything to the vault. The `summarize_ddg/` directory in
`user_vault/<node_id>/` contained only the runner log file. The summary was
recorded in the queue's `done` event outputs, but that column is not meant for
large payloads and is invisible to downstream steps that look for a vault URI.

## Fix

`work()` now serialises the result payload as JSON and saves it via
`vault.store()` before returning. The returned dict gains a `summary_uri` key
pointing to the new file, mirroring the pattern used by `fetch_ddg`.

The saved JSON includes:

```json
{
  "status": "...",
  "summary": "...",
  "model": "...",
  "version": "...",
  "prompt": "..."
}
```

`prompt` was also missing from the earlier return dict — it is now included so
the full LLM input is preserved alongside the output for auditability.

The file is pretty-printed (`indent=2`, `ensure_ascii=False`) for readability.

## Version bump

`SummarizeDdgStep.version` was `SUMMARIZE_VERSION` (a hash of the system prompt
+ model + blacklist). It is now `SUMMARIZE_VERSION + ".2"` to invalidate
existing `done` queue entries so affected nodes are re-run and get a proper
vault file.

## Changes

**`anpe/engine/steps/summarize_ddg.py`**
- `work()`: add `vault.store()` call, include `prompt` in payload, return
  `summary_uri` in outputs dict.
- `version`: append `.2` suffix.
