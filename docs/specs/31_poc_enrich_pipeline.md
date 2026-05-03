---
status: done
---

# POC — Enrichment pipeline

Simplified implementation goal. Get the core fetch → summarize loop working on one
real company before adding profile, triage, multi-node, or agent integration.

## Goal

Run `enrich()` on a single node, see what the LLM produces, validate that the loop
is useful. Every open design question gets answered by looking at real output, not
by reasoning in the abstract.

## Fetch tool registry

Fetch methods are registered by slug in a single dict. The queue stores `(slug, target)`
pairs; `enrich` dispatches to the right function at runtime.

```python
FETCH_TOOLS: dict[str, Callable[[str], str]] = {
    "ddg":    ddg_search,    # DuckDuckGo text search via ddgs lib
    # "siren":  siren_fetch, # SIRENE API — deferred
    # "fetch":  http_fetch,  # raw HTTP GET — deferred
    # "tavily": tavily_fetch, # Tavily advanced capture — deferred
}
```

Each function has the same signature: `(target: str) -> str` — it receives the query
or URL and returns raw text. Error handling (timeout, HTTP error, …) is the function's
responsibility; it raises on failure so the caller can log and skip.

Only `ddg` is implemented in the POC. Adding a new tool = adding one entry to the dict.

## The loop

```python
# bootstrap — called once to initialize the node
queue = [
    ("ddg", company_name),
]

def enrich():
    next_target = queue.get()
    if next_target is None:
        return

    tool_slug, target = next_target
    fetch_fn = FETCH_TOOLS[tool_slug]
    data = fetch_fn(target)          # raises on error

    previous_summary = get_summary()
    status, new_summary, new_targets = llm_summarize(data, previous_summary)

    if status == "not_relevant":
        log("not_relevant")
        return

    log("ok")
    save_summary(new_summary)
    queue.put(new_targets)           # new_targets: list[tuple[str, str]]
```

## `llm_summarize`

Single LLM call. Input: raw fetch data + previous summary. Output: status, updated
summary, list of next targets to add to the queue.

No user profile for now — the prompt includes a hardcoded intent to make the summary
meaningful during testing:

> _"We are looking for small French tech companies doing AI or software work."_

The profile slot replaces this string later. Nothing else changes.

`new_targets` is a list of `(tool, url_or_query)` pairs the LLM identified as worth
fetching next (e.g. a website URL found in DDG results, a LinkedIn page).

## CLI commands (POC)

```bash
anpe add_target NODEID ddg KEYWORD   # append a fetch target to the node
anpe enrich NODEID                    # advance one step: fetch if pending, summarize if fetch_done
anpe summarize NODEID [FETCH_UID]     # re-run summarize on existing fetch data, bypass queue
```

`enrich` runs **one step** so output can be inspected between cycles.
`add_target` takes the tool slug explicitly — it must exist in `FETCH_TOOLS`.
`summarize` is for prompt tuning — it reads the raw file already on disk and calls
`llm_summarize` again, writing a new result file under `summarize/`. No network call.

## Storage

Node directory layout:

```
user_data/nodes/<node_id>/
  fetch.jsonl          — state machine log (append-only, events: put | fetch_done | summarize_done | …)
  summary.md           — current summary, overwritten on each update
  raw_data/            — raw fetch output, one file per completed fetch
  summarize/           — one result file per process run, linked from fetch.jsonl
    sum_<tool>_<target>_<status>_<ts>.json
    prompt_<tool>_<target>_<ts>.txt   — LLM prompt captured for debugging (temporary)
```

### fetch.jsonl — state machine log

Each line is one event; state reconstructed by replay, file never rewritten.
The unit of work is one full `fetch → summarize` cycle per target.

State machine per `uid`:

```
put → fetch_done → summarize_done   (happy path)
    → fetch_error                   (terminal — fetch failed)
    → fetch_done → summarize_error  (retryable — re-run summarize without re-fetching)
```

```jsonl
{"event": "put",             "uid": "a3f1", "tool": "ddg", "target": "Hugging Face", "ts": "..."}
{"event": "fetch_done",      "uid": "a3f1", "raw_file": "raw_ddg_Hugging_Face_20260501T162300.txt", "ts": "..."}
{"event": "fetch_error",     "uid": "a3f1", "detail": "DDG returned no results", "ts": "..."}
{"event": "summarize_done",  "uid": "a3f1", "model": "openai/gpt-4o-mini", "status": "ok", "result_file": "sum_ddg_Hugging_Face_ok_20260501T162301.json", "ts": "..."}
{"event": "summarize_error", "uid": "a3f1", "detail": "429 rate limit", "ts": "..."}
```

A target is pending if its latest event is `put` or `summarize_error`. `enrich` dispatches
based on state: fetches if `put`, summarizes directly if `fetch_done` / `summarize_error`.

`summarize_error` is the key case: fetch data is already on disk, so `enrich` (or
`anpe summarize`) can retry the LLM step without hitting the network.

### summarize/ — per-run result files

One JSON file per process run. Named `sum_<tool>_<target>_<status>_<ts>.json` —
readable by browsing the directory, and linked from the `summarize_done` event in
`fetch.jsonl` via `result_file`.

```json
{
  "ts": "...",
  "fetch_uid": "a3f1",
  "model": "openai/gpt-4o-mini",
  "status": "ok",
  "summary": "...",
  "new_targets": [{ "tool": "fetch", "target": "https://..." }]
}
```

For LLM-backed tools, a companion `prompt_<tool>_<target>_<ts>.txt` is written
alongside with the exact prompt sent — useful for prompt tuning, to be removed later.

## What we want to learn

- Does the LLM produce useful summaries from SIRENE + DDG data?
- Does it propose sensible next targets?
- How many fetch cycles does it take to get a meaningful picture of a company?
- Where does it get stuck or produce noise?

## Insights

Design decisions made during implementation:

**Append-only event log for the queue.** The initial design stored status directly on
each queue entry and rewrote lines in-place on completion. Switched to an event log
(`put` / `done` / `error`) with a `uid` per target. Benefits: no file mutation, full
history preserved, `raw_file` pointer on `done` keeps fetch artifacts linked to the
event that produced them. State is reconstructed by replaying events forward.

**`uid` is random hex, not a hash of tool+target.** A hash looks deterministic but
adds no value (you never look up by it), and breaks if the same target is queued
twice intentionally.

**`fetch.jsonl` as state machine, `summarize/` as result files.** `fetch.jsonl` is kept
light: it only tracks lifecycle events (`put` → `fetch_done` → `summarize_done/error`).
Full LLM output lives in one JSON file per run under `summarize/`, named
`sum_<tool>_<target>_<status>_<ts>.json` and linked from `fetch.jsonl` via `result_file`
(mirroring how `raw_file` links raw fetch artifacts). Browsing `summarize/` gives a
human-readable history without parsing the event log. Re-running `anpe summarize` after
a prompt change produces a new file each time — history is preserved, `fetch.jsonl`
always points to the latest.

**`summarize_error` enables clean retry without fake events.** When the LLM call fails
(quota, rate limit), the target stays in `fetch_done` state and `enrich` retries the
summarize on the next call. No need to inject fake events or re-fetch.

## Next session — prompt tuning

The loop runs end-to-end. The blocking gap is that `llm_summarize` rarely proposes
`new_targets`, so the loop stops after one step instead of following up with the
company website or a more specific DDG query.

**Goal:** get `new_targets` working reliably so the loop chains 2-3 fetch steps on its own.

### What to do

1. Test on 3-4 real companies, inspect `summarize/` result files for each.
2. For each case where `new_targets` is empty: look at the raw DDG data — were there
   obvious URLs or names to follow up on? If yes, the prompt is failing to extract them.
3. Iterate on the system prompt in `anpe/enrich/summarize.py`. Use `anpe summarize NODEID`
   to re-run the LLM on existing fetch data — no re-fetching needed.
4. Add the `fetch` tool (raw HTTP GET, `httpx`) so LLM-proposed website URLs can
   actually be fetched. Without it, `new_targets` with `"fetch"` are silently dropped.

### What good looks like

- DDG step produces 1-2 follow-up targets (company website, or a more specific query)
- `fetch` step on the website produces a richer summary
- `not_relevant` threshold feels correctly calibrated (Veolia: yes, Synapse: no)

### Lower priority for now

- SIREN fetch (DDG already covers basic company info)
- Agent integration (too early, loop quality not validated yet)
- Error handling improvements (good enough for manual testing)
- User profile replacing hardcoded intent
