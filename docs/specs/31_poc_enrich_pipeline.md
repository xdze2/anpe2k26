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

## The loop

```python
# bootstrap — called once to initialize the node
queue = [
    (sirene_fetch, siren_id),
    (ddg_search,   company_name),
]

def enrich():
    next_target = queue.get()
    if next_target is None:
        return

    return_code, data = tool_call(next_target)

    if return_code == error:
        log(error)
        return

    previous_summary = get_summary()
    status, new_summary, new_targets = llm_summarize(data, previous_summary)

    if status == "not_relevant":
        log("not_relevant")
        return

    log("ok")
    save_summary(new_summary)
    queue.put(new_targets)
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

## Storage

Minimal. Two files per node:

- `summary.md` — current summary, overwritten on each update
- `queue.jsonl` — append-only, one entry per target, fields: `status`, `tool`, `target`, `ts`

No `enrichment.jsonl` for now. Logging goes to stdout or a simple text log.

## What we want to learn

- Does the LLM produce useful summaries from SIRENE + DDG data?
- Does it propose sensible next targets?
- How many fetch cycles does it take to get a meaningful picture of a company?
- Where does it get stuck or produce noise?

## Explicitly deferred

- User profile (replaced by hardcoded intent)
- Match delta / triage verdict
- `revisit` surfacing
- Multi-node / background worker
- Agent integration
- `enrichment.jsonl` audit log
