# 2026-05-03 — prospect list command and prompt version tracking

## What was done

### `anpe prospect list`

New CLI command giving a one-line-per-node overview of the full pipeline state:

```
anpe prospect list
```

For each node (ordered by creation time) it prints:
- node id
- last event state (color-coded: green = summarize_done, yellow = put/pending, cyan = fetch_done, red = error)
- pending target count if any
- model + prompt version tag used in the most recent summarize_done
- first line of `summary.md` as a context hint

### Prompt version tracking (`PROMPT_VERSION`)

`summarize.py` computes `PROMPT_VERSION = sha1(_SYSTEM)[:6]` at import time
(currently `155fa7`). It is stored in every `summarize_done` event in
`fetch.jsonl`:

```json
{"event": "summarize_done", ..., "model": "mistral-small-2603", "prompt_version": "155fa7", ...}
```

The hash changes automatically when `_SYSTEM` is edited — no manual bump.
Existing records keep their old hash (or no hash for pre-feature records),
making it possible to identify which results were produced with which prompt
revision.

## Next

- Wire `company_profile` into the production pipeline (`NodeDir.get_company_profile()`).
- Re-run eval after `no_data` prompt hardening to verify medium/14b compliance
  (not a blocker — `mistral-small-2603` is the selected model).
