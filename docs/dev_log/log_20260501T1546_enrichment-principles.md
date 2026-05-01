# 2026-05-01 — Enrichment principles rewrite

## What changed

Rewrote `docs/specs/20_principles.md` from scratch. Previous version had two conflicting
pipeline models (a dynamic `next_fetch_target(node_summary)` and a fixed source sequence)
and a leftover `rank_delta` concept that didn't correspond to anything in the design doc.

Key decisions made or clarified:

**Pipeline structure.** `enrich(node)` has three sub-steps:
`next_fetch_target` → `fetch` → `eval`. One cycle per call.

**`next_fetch_target` is a LLM call, not hardcoded logic.** Input is the full node state
(all previous evals and summaries). Output is a ranked list of candidates, each with a
tool+URI, rationale, and estimated information gain. Cost ordering is enforced via the
prompt (available tools listed with costs), not via sequencing logic in the dispatcher.
This keeps the dispatcher generic and makes the pipeline extensible past DDG without
special-casing.

**4 eval layers, not 3.** The previous version collapsed "content value" and "new
information" into one layer. They are distinct: a fetch can return content that is
relevant to the company but already captured in the summary (layer 2 passes, layer 3
stops). Separated cleanly:
1. Data quality (`ok / not_found / retryable / blocked`)
2. Content value (`relevant / not_relevant`)
3. New information (`new / known`) — triggers summary rewrite when `new`
4. Match delta (`no_change / revisit / discard`)

**Match delta reframed.** Layer 4 is a filter for user attention, not a scoring step.
`revisit` carries a specific reason ("found 500 employees; you said small teams only").
The user sees the delta, not a data dump. The verdict is always owned by the user —
eval only flags when it might need updating.

**Summary is user-relative.** The node summary is an interpretation for this user, not
an objective company description. Filtering by profile relevance is the right direction
but deferred to prompt design.

## Still open

- `docs/specs/20_principles.md` is marked `draft` — still needs work. It is now the
  canonical reference for enrichment logic; `42_enrichment_design_v2.md` has more detail
  but predates these decisions and needs reconciling.
- How many LLM calls implement the 4 layers (one call vs. one per layer) — left open,
  implementation detail.
- Node merge / identity resolution (same company under two SIRENs) — out of scope.
- Agent interaction model (interactive vs autonomous modes) — deferred, not in principles.
