---
status: draft
---

# Principles

High-level design. How the vision translates into a system: the main components, data flows, and logic. No storage or implementation detail.

## Data vault

Two kinds of persistent state:

**User profile** — what the user is looking for: target roles, preferred company sizes, sectors, dealbreakers. Read at startup; updated as the user reacts to companies. Short by design — an interpretation of the user's intent, not a log of everything they've ever said.

**Nodes** — one node per candidate company. A node starts as a bare seed (a SIREN code) and grows as information is collected. It holds:

- a summary of everything gathered so far, written from the user's point of view
- the user's triage verdict
- the current list of next fetch candidates
- all raw fetched data (never deleted — kept for cache, replayability, and debugging)

## Enrichment pipeline

One entry point: `enrich(node)`. It runs one fetch → eval cycle and updates the node.

```
enrich(node):
  target = next_fetch_target(node)   ← decided by LLM, from full node state
  raw    = fetch(target)             ← tool call: SIRENE, DDG, HTTP, Tavily, ...
  result = eval(raw, node, profile)  ← LLM eval, 4 layers (see below)
  update node with result
```

Raw data is never surfaced directly to the user.

The pipeline is oriented toward positive matches: among many candidates, few will be strong positives. Stopping early on confirmed negatives is the default.

### `next_fetch_target`

Decides what to fetch next, given the full current state of the node (all previous evals and summaries) and the list of available fetch tools with their costs.

Output: a ranked list of candidates, each with:

- the tool and URI to call
- a short rationale ("LinkedIn URL found in DDG snippet")
- an estimated information gain ("likely has headcount and tech stack")

The dispatcher auto-picks the top candidate in autonomous mode. In interactive mode the list can be surfaced to the user.

This is a LLM call. The prompt includes the available tools and their costs, so the LLM naturally respects cost ordering without hardcoded sequencing logic.

### Fetch

A tool call. Each source has a fixed interface: takes a URI (or a query), returns raw data and a fetch status.

| Source           | Cost                                             |
| ---------------- | ------------------------------------------------ |
| SIRENE API       | free, rate-limit friendly                        |
| Web search (DDG) | free, best first-pass for small French companies |
| Website fetch    | free, but fails on Cloudflare / JS-heavy sites   |
| Tavily search    | paid (1000 req/month quota) — post-interest only |
| ...              | ...                                              |

Adding a new source follows the same pattern every time. No structural changes needed.

### Eval — 4 layers

Every fetch is followed by an eval step (LLM). The four layers run in sequence; later layers are skipped if an earlier one stops the pipeline.

**Layer 1 — Data quality**

Did the fetch return usable content?

| Value       | Meaning                   | Action                  |
| ----------- | ------------------------- | ----------------------- |
| `ok`        | usable content            | proceed                 |
| `not_found` | 404, empty, no results    | stop — log and move on  |
| `retryable` | network error, rate limit | stop — retry later      |
| `blocked`   | Cloudflare, CAPTCHA       | stop — needs a code fix |

**Layer 2 — Content value**

Is there anything relevant to this company here?

| Value          | Meaning                         | Action  |
| -------------- | ------------------------------- | ------- |
| `relevant`     | content applies to this company | proceed |
| `not_relevant` | wrong company, empty content    | stop    |

**Layer 3 — New information**

Is this new relative to what the node summary already captures?

| Value   | Meaning              | Action                   |
| ------- | -------------------- | ------------------------ |
| `new`   | not previously known | proceed — update summary |
| `known` | already captured     | stop — no update needed  |

When `new`: the node summary is rewritten to incorporate the new information. The summary is always relative to the user profile — it is an interpretation for this user, not an objective company description.

**Layer 4 — Match delta**

Given everything now known about the node, does the user's current verdict still hold? This layer looks at the full node state, not just the new data.

| Value       | Meaning                                  | Action                             |
| ----------- | ---------------------------------------- | ---------------------------------- |
| `no_change` | new info consistent with current verdict | continue silently                  |
| `revisit`   | new info that could shift the verdict    | surface to user with reason        |
| `discard`   | clearly negative signal                  | stop pipeline; mark node discarded |

`revisit` carries the reason — the specific new signal that warrants user attention ("found 500 employees; you said small teams only"). The user is shown the delta, not the full data dump.

The verdict itself is always owned by the user. The eval never sets it — it only flags when it might need updating.

## Triage

Each node carries a user verdict:

| Status       | Meaning                      |
| ------------ | ---------------------------- |
| `to_look_at` | candidate, not yet evaluated |
| `discarded`  | confirmed not relevant       |
| `good`       | interesting                  |
| `very_good`  | strong match                 |

Set by the user directly, or proposed by the agent from eval results. The agent proposes; the user confirms or corrects.
