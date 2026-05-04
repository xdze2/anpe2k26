# 2026-05-04 — Prompt tuning, DDG raw storage, and CLI cleanup

## Commits not covered by previous log entries

### DDG fetch: save raw JSON, filter blacklist in summarize step (983f73a)

`ddg_search` now returns the raw DDGS output as indented JSON, saved as `.json`
(was plain text). The `DIRECTORY_BLACKLIST` moved from the fetch step into
`summarize.py`: `_format_ddg_results()` applies it when building the LLM prompt,
so raw data on disk is never filtered — only the prompt is.

Blacklist content is included in the `SUMMARIZE_VERSION` hash alongside the system
prompt and model name, so adding a domain to the blacklist automatically invalidates
existing summaries.

### Indent json save (8411847)

`siren_fetch` now saves indented JSON for readability. Cosmetic only.

### Improve ddg_summarize prompt: header line + no filler (af694c3)

Added a structured header line at the top of each summary:

```
**Type**: <nature> · **Domaine**: <sector> · **Marché**: <clients>
```

Fields left empty if the data doesn't support a confident answer.
Banned filler sections: "Key insights", "Next steps", "Potential fit", and
any closing sentence about why the company "appeals to tech professionals" —
that judgement belongs to the user.

---

## CLI cleanup and resummarize (this session)

### Removed `step` command

`anpe prospect step <node_id>` was identical to `anpe prospect run -n 1 <node_id>`.
Removed.

### Replaced `summarize` with `resummarize`

The old `summarize` command force-re-ran the summarize step on a specific node,
bypassing the queue. Replaced by `resummarize`, which:

1. Scans nodes for `summarize_done` entries whose `summarize_version` in the
   `sum_*.json` file no longer matches the tool's current version constant.
2. Appends a `resummarize` event on the same uid (no new fetch uid needed —
   the existing `fetch_done` is still valid).
3. The next `anpe prospect run` picks it up via `pop_pending` and skips straight
   to the summarize step (raw file already on disk).

### `FetchTool.version` field

Each tool now declares its own `version` string in `registry.py`. This was
necessary because `siren_summarize` has its own version logic (deterministic,
no LLM) and was hardcoding `"v1"` — disconnected from `SUMMARIZE_VERSION` in
`summarize.py`. The staleness check in `get_stale_summarize_uids` now dispatches
per tool.

`siren_summarize` bumped to `SIREN_SUMMARIZE_VERSION = "v2"`.

### `resummarize` event in `fetch.jsonl`

New event type. Carries the original uid (same uid as the `fetch_done` and
`summarize_done` it supersedes). `pop_pending` recognises it alongside `put`
and `summarize_error`. A `reason` field is written (currently always
`"version_change"`).

## Next

- The `status` command (per-node fetch history detail) could be renamed `show`
  or `inspect` to avoid confusion with `list` — deferred.
- `resummarize` currently only handles version staleness. Other future causes
  (corrupted file, manual override) would reuse the same event with a different
  `reason`.
