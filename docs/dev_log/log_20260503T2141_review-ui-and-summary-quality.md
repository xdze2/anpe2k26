# 2026-05-03 — Review UI and summary quality

## What was done

### `anpe prospect review` — terminal review loop

New CLI command to page through summarized nodes and record a free-text reaction:

```
anpe prospect review
```

For each node with `summarize_done` and no prior review, displays:
- header rule: index/total, company name, meta (city · headcount · NAF)
- summary body rendered as rich Markdown, padded 6 chars each side
- next targets line (up to 3, dim): signals what the pipeline would fetch next

Input: one line of free text, Enter to save. Empty Enter = skip (reviewable again
later). `q` to quit at any time.

Reactions are stored in `reviews.jsonl` (append-only, per node), same pattern as
`fetch.jsonl`. No frontmatter changes yet — the log is the source of truth.

```jsonl
{"ts": "...", "reaction": "trop corporate mais tech stack intéressante"}
{"ts": "...", "skip": true}
```

`is_reviewed()` = latest event has a non-empty reaction (not a skip).
`has_summarize_done()` = any fetch cycle reached `summarize_done` with status `ok`
or `no_data`.

Also fixed a pre-existing bug: `prospect list` was calling `node.get_summary()`
which didn't exist — corrected to `node.get_summary_body()`.

## Observed problem — summary noise

Looking at real summaries, two categories of noise:

**1. Redundant data** (already in frontmatter):
- NAF code + label repeated in the body
- Size, city, category restated in prose
- Company name as H1 title

**2. Generic LLM filler**:
- "Key insights for tech professionals:" sections
- "Key takeaway:", "Potential fit for tech professionals seeking..."
- "appeals to tech professionals interested in..."
- "making it a compelling target for..."

The body should be information-dense and minimal. The fix belongs in the prompt
(negative rules), not post-processing. Re-running with `anpe prospect summarize`
requires no re-fetch.

**Missing structured fields** — NAF tells you nothing useful. What matters:

| Dimension | Values |
|---|---|
| Type | éditeur / ESN-prestataire / conseil / produit+conseil |
| Domaine | e-commerce, mobilité, RH, cybersécurité, spatial, énergie... |
| Marché | B2B, B2C, B2G, mixte |

These three should appear as a compact header line in the summary body, not prose.
The rest of the body only contains what isn't obvious from the header + frontmatter.

## Discussion — ranking and feedback loop

### Free-text reaction vs numeric ranking

Settled on free-text (one line) rather than a numeric scale. Rationale: the
bottleneck in the review loop is time to understand the summary, not time to type.
A few words ("trop corporate", "exactement ce que je cherche", "trop grande mais
domaine intéressant") carry more signal for the LLM extraction step than a +2.
Numeric ranking can always be derived from the text by the LLM later.

### Signal extraction from reactions

Planned LLM step (not yet implemented): `rank_feedback(summary, reaction,
current_profile) → list[ProfileDelta]`. Each delta is a structured update to the
profile (add / reinforce / contradict a belief), with a confidence level and a
reason. Low-confidence deltas are held until reinforced by more reactions.
High-confidence ones are applied immediately.

The profile stays a short human-readable markdown document — the LLM writes
updates as natural language edits, not structured patches. Always editable and
correctable by the user directly.

### Embedding-based similarity (considered and deferred)

Discussed embedding summaries + nearest-neighbor matching as a scoring mechanism.
Rejected as primary engine for this stage:
- Requires ~50-100 ranked nodes before factorization becomes meaningful
- Opaque: can't explain why a company is recommended
- Underdetermined with a single user (can't separate orthogonal features)

Could be useful later as a consistency check ("this company resembles one you
already discarded") once enough reactions have accumulated.

### Node-level validity / staleness (design direction)

Identified that the current state machine is fetch-scoped (`put → fetch_done →
summarize_done`) but doesn't model higher-level staleness. Two independent
validity dimensions are needed on the node:

```
summary_status:  fresh | stale | pending_fetch
score_status:    fresh | stale | missing
```

`stale` is triggered externally (profile changed → all scores become stale), not
by a fetch cycle. A `score` step will output one of:
`discard | to_look_at | good | very_good | not_enough_info`.

`not_enough_info` routes back to the pipeline (enqueue more fetch steps) rather
than surfacing to the user.

## Next

- Rewrite the summarize prompt: ban redundant fields, ban filler phrases, add
  structured type/domaine/marché header line.
- Add eval fixture: thin DDG result with only frontmatter-level info → expected
  `no_data`.
- Implement the `score(node, profile)` step (Layer 3 from spec).
- Implement `rank_feedback` for profile updates from reactions.
