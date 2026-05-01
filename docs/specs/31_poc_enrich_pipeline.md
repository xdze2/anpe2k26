---
status: draft
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

> *"We are looking for small French tech companies doing AI or software work."*

The profile slot replaces this string later. Nothing else changes.

`new_targets` is a list of `(tool, url_or_query)` pairs the LLM identified as worth
fetching next (e.g. a website URL found in DDG results, a LinkedIn page).

## CLI commands (POC)

```bash
anpe add_target NODEID ddg KEYWORD   # append a fetch target to the node
anpe enrich NODEID                    # pop one item, fetch, llm_summarize, save
```

`enrich` runs **one step** so output can be inspected between cycles.
`add_target` takes the tool slug explicitly — it must exist in `FETCH_TOOLS`.

## Storage

Node directory layout:

```
user_data/nodes/<node_id>/
  fetch.jsonl       — fetch log / cache (append-only, events: put | done | error)
  summarize.jsonl   — summarize log (append-only, one entry per LLM call)
  summary.md        — current summary, overwritten on each update
  raw_data/         — raw fetch output, one file per completed fetch
```

### fetch.jsonl — fetch log / cache

Each line is one event; state reconstructed by replay, file never rewritten.
A target is pending if it has a `put` with no matching `done` or `error`.

```jsonl
{"event": "put",   "uid": "a3f1", "tool": "ddg", "target": "Hugging Face", "ts": "..."}
{"event": "done",  "uid": "a3f1", "raw_file": "raw_ddg_Hugging_Face_20260501T162300.txt", "ts": "..."}
{"event": "error", "uid": "a3f1", "detail": "DDG returned no results", "ts": "..."}
```

`uid` is short random hex. The `raw_file` pointer on `done` links the event to its artifact.
`fetch.jsonl` acts as a **cache**: if a target is already `done`, the fetch can be skipped
and summarization re-run on the existing raw file (e.g. after a prompt change).

### summarize.jsonl — summarize log

One entry per LLM call. Records model, status, output, and which fetch it consumed.

```jsonl
{"ts": "...", "fetch_uid": "a3f1", "model": "openai/gpt-4o-mini", "status": "ok",
 "summary": "...", "new_targets": [{"tool": "fetch", "target": "https://..."}]}
```

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

**fetch.jsonl as a cache, summarize.jsonl as a separate log.** Separating fetch and
summarize logs allows re-running the LLM on already-fetched data (e.g. after a prompt
change) without hitting the network again. The `fetch_uid` field in `summarize.jsonl`
links each LLM call back to the fetch that produced the input data.

## Explicitly deferred

- User profile (replaced by hardcoded intent)
- Match delta / triage verdict
- `revisit` surfacing
- Multi-node / background worker
- Agent integration
- `enrichment.jsonl` audit log
- Additional fetch tools: `siren`, `fetch` (raw HTTP), `tavily`, …
