---
status: draft
---

# User review and profile update

The feedback loop: the user reacts to company summaries, and those reactions are
synthesised into an updated search profile. The profile in turn drives eval scoring
and candidate selection.

---

## User review (`anpe prospect review`)

The user is shown a node's summary and reacts in free text. The reaction is stored
in `reviews.jsonl` — append-only per node.

```jsonl
{"ts": "...", "reaction": "exactement ce que je cherche, NewSpace petit"}
{"ts": "...", "skip": true}
{"ts": "...", "reaction": "trop ESN, pas de produit propre"}
```

A node is considered reviewed when its latest event has a non-empty `reaction`.
Skipped nodes reappear in the next review session.

The user and the LLM share exactly the same information: the summary body. No
browser, no external context. Reactions are only as good as the summary.

---

## Profile update (`anpe profile update`)

### Call shape

Single LLM call with all reactions not yet incorporated into the current profile:

```
system:
  You are updating a job-search profile based on the user's reactions to company
  summaries. Be conservative — only update what the reactions clearly support.
  Return the full updated profile text.

user:
  Current profile:
  <current profile content>

  Recent reactions:
  - [INFINITE ORBITS] NewSpace, 20p, Toulouse — "exactement ce que je cherche"
  - [ALTECA] ESN, 500p — "trop grande, trop ESN"
  - [BIGBLUE] logistics SaaS, 50p — "intéressant, bon domaine"
```

Output: full updated profile text. The user can diff and edit before saving.

### Storage

Each update writes a new timestamped file — profiles are immutable records (see
`12_data_flow.md`). The active profile is the most recent by filename timestamp.

```
user_data/
  profile_20260505T1200.md   ← previous, never modified
  profile_20260506T0900.md   ← current active
```

### Tracking incorporated reactions

The profile file carries a frontmatter timestamp:

```yaml
---
updated_ts: 2026-05-05T12:00:00Z
---
```

`profile update` collects reactions from all nodes whose `reviews.jsonl` has
entries newer than `updated_ts`. Older reactions are already incorporated.

### Why batch synthesis

The LLM sees all reactions at once and can detect cross-reaction patterns that
incremental updates miss — e.g. "user rejected 4 ETIs with the same wording,
and reacted positively to all companies under 30 people". Per-reaction updates
lose this signal.

### After profile update

A `reeval` scan is triggered: all nodes whose last eval used an older profile
file are re-queued. See `34_llm_eval_step.md`.
