# 2026-05-05 — User profile demo + LLM eval design

## Profile update from user reactions

Ran a manual demo of the profile update flow: fed 41 company reactions into the
profile updater prompt and wrote the result to `user_data/profile.md`.

Example reactions used (anonymized):

- [NOVA SYSTEMS] BORDEAUX · 50-99 — "no"
  digital agency, web dev and e-commerce
- [DATAVISION] PARIS · 100-199 — "maybe"
  software editor, AI and data analytics, crisis management
- [ORBITECH] TOULOUSE · 20-49 — "yes"
  deep tech, in-orbit servicing, autonomous navigation, AI
- [SYNBOT] TOULOUSE · 10-19 — "yes"
  chatbots, AI, specialized recruitment platform
- [GEOFLOW] TOULOUSE · 10-19 — "nice, smartmap app (geo + commerce)"
  geospatial software, isochrones, catchment area analysis
- [CLOUDPATH] TOULOUSE · 20-49 — "no, cloud only"
  ESN specialized in cloud and DevOps

The resulting profile captures:

- **Positive**: IA/data/deep tech, scientific/engineering domains (space, mobility,
  geospatial, AR), open source SaaS, B2B product companies with technical substance
- **Dealbreakers**: commerce/retail as core domain, finance, healthcare/pharma,
  real estate, pure web agencies, IT infra/monitoring only, marketing analytics

### Observations on data quality

The reaction set was almost entirely sector-based rejections. The profile can
eliminate ~70% of companies but lacks signal for ranking the remaining 30%:

- No role/seniority signal (data scientist? ML engineer? research?)
- "maybe" reactions gave no elaboration — wasted signal
- Positive reactions were too few and varied to triangulate a positive archetype
- "tech non intéressante" used repeatedly without a concrete counter-example

### Proposed improvement: pairwise comparison

Comparative ranking is easier for the user than absolute scoring (no opportunity
cost to evaluate). Proposed: after the profile update runs, if ≥2 positive
companies are accumulated, trigger 1-2 pairwise questions:

> "Quick compare: ORBITECH vs SYNBOT — which fits you better, and what's the
> deciding factor?"

Pair selection strategy (most informative pairs):

- yes vs maybe → resolves ambiguous cases
- two yeses from different apparent reasons → surfaces which dimension matters more
- yes vs borderline no → stress-tests a dealbreaker

Implementation: a second tool called after `update_search_profile`, emitting
comparison questions when the positive pool is large enough. Stays inside the
existing reaction loop, no new commands needed.

---

## LLM eval tool design

Next step: automate company evaluation against the user profile, to pre-score
unseen companies before the user sees them.

### Output format

```
score: 3/5
fit: "strong IA angle matches well, but core domain is logistics — borderline on commerce dealbreaker"
dealbreakers: ["retail-adjacent"]
uncertainty: medium
```

Fields:

- `score` (1–5) — drives ranking
- `fit` — one sentence naming the deciding factor; user reads this to validate or override
- `dealbreakers` — explicit list; any hit means skip regardless of score
- `uncertainty` — low/medium/high; flags thin summary data ("no data" cases)

### Design decisions

**Dealbreaker check is a separate pass from scoring.** A single-shot prompt that
combines both tends to let a high score override an obvious dealbreaker. Explicit
field prevents that drift.

**Scores should be sparse.** A flat 3/5 distribution makes ranking useless.
Alternative: 3-level scale (`skip / maybe / strong`) maps directly to existing
user vocabulary and forces a real distribution.

**`fit` sentence matters more than the score.** It's the user's correction surface —
if the sentence is wrong, the correction improves the profile. No long reasoning
chain; one sentence forced to name the deciding factor.

## Next

- Implement `compare_companies` tool (post-profile-update pairwise questions)
- Implement LLM eval step in the prospect pipeline, outputting score + fit + dealbreakers
