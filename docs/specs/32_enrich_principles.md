---
status: draft
---

# Principles

High-level design. How the vision translates into a system: the main components, data flows, and logic. No storage or implementation detail.

## Enrichment pipeline

One entry point: `enrich(node)`. It runs one fetch → eval cycle and updates the node.

```
enrich(node):
  target = next_fetch_target(node)   ← hybrid: fixed order first, then LLM
  raw, status = fetch(target)        ← tool call; returns data + fetch status
  if status != ok: stop              ← fetch-level check, no LLM needed
  result = eval(raw, node, profile)  ← LLM eval, 3 layers (see below)
  update node with result
```

Raw data is never surfaced directly to the user.

The pipeline is oriented toward positive matches: among many candidates, few will be strong positives. Stopping early on confirmed negatives is the default.

### `next_fetch_target`

Decides what to fetch next. The first two steps are always fixed:

1. SIRENE API — the seed; always first
2. DDG web search — best free first-pass for small French companies

After that, the LLM decides based on the full node state (previous evals, summaries, candidate URLs found so far) and the list of available tools with their costs. The prompt includes cost information so the LLM naturally respects cost ordering without hardcoded sequencing logic.

Output: a ranked list of candidates, each with a tool, a URI or query, a short rationale, and an estimated information gain. The dispatcher auto-picks the top candidate in autonomous mode. In interactive mode the list can be surfaced to the user.

### Fetch

A tool call. Each source has a fixed interface: takes a URI or query, returns raw data and a fetch status.

Fetch status (returned by the tool, no LLM involved):

| Status      | Meaning                   | Action                |
| ----------- | ------------------------- | --------------------- |
| `ok`        | usable content returned   | proceed to eval       |
| `not_found` | 404, empty, no results    | log and move on       |
| `retryable` | network error, rate limit | retry later           |
| `blocked`   | Cloudflare, CAPTCHA       | surface — needs a fix |

| Source           | Cost                                             |
| ---------------- | ------------------------------------------------ |
| SIRENE API       | free, rate-limit friendly                        |
| Web search (DDG) | free, best first-pass for small French companies |
| Website fetch    | free, but fails on Cloudflare / JS-heavy sites   |
| Tavily search    | paid (1000 req/month quota) — post-interest only |
| ...              | ...                                              |

Adding a new source follows the same pattern every time. No structural changes needed.

### Eval — 3 layers

Every successful fetch is followed by an LLM eval. The three layers run in sequence; later layers are skipped if an earlier one stops.

**Layer 1 — Content value**

Is there anything relevant to this company here?

| Value          | Meaning                         | Action  |
| -------------- | ------------------------------- | ------- |
| `relevant`     | content applies to this company | proceed |
| `not_relevant` | wrong company, empty content    | stop    |

**Layer 2 — New information**

Is this new relative to what the node summary already captures?

| Value   | Meaning              | Action                   |
| ------- | -------------------- | ------------------------ |
| `new`   | not previously known | proceed — update summary |
| `known` | already captured     | stop — no update needed  |

When `new`: the node summary is rewritten to incorporate the new information. The summary is always relative to the user profile — it is an interpretation for this user, not an objective company description. The eval also updates the list of next fetch candidates.

**Layer 3 — Match delta**

Given everything now known about the node, does the user's current verdict still hold?

| Value       | Meaning                             | Action                             |
| ----------- | ----------------------------------- | ---------------------------------- |
| `no_change` | consistent with current verdict     | continue silently                  |
| `revisit`   | new signal that could shift verdict | surface to user with reason        |
| `discard`   | clearly negative signal             | mark node discarded; stop pipeline |

`revisit` carries the specific reason ("found 500 employees; you said small teams only"). The user is shown the delta, not the full data dump.

`discard` is applied by the pipeline automatically — there are too many negative nodes to surface each one. But the user can always override a pipeline verdict. The verdict is ultimately owned by the user; the pipeline acts as a first pass.
