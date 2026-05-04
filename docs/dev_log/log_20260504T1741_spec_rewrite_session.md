# Spec rewrite session

## What happened

Started a fresh in-depth review of the project specification, treating all existing docs
as outdated. The goal is to rewrite the spec from scratch, in reading order.

### `10_vision.md` — done, status: active

Two significant changes from the previous version:

- Renamed "How it works" → "An exploration assistant". The section was rewritten to lead
  with the SIRENE data problem (purely administrative, no signal) before explaining the
  loop. The key insight: the challenge is not finding candidates, it's navigating a space
  too large and undifferentiated to filter before enriching.
- Added the exploration framing explicitly: the user doesn't fully know what they're
  looking for yet — the right match may be a surprise. This justifies the loop structure
  over a batch approach.

### `11_exploration_loop.md` — created, status: draft

New doc. Contains:

- Intro paragraph establishing no fixed session boundary — the loop runs at whatever
  pace the user can sustain.
- Loop flow diagram (Mermaid): bootstrap → enrich → review → eval (rank) → enrich.
  The EVAL step (LLM re-ranks all candidates after each review) is explicit.
- Candidate states diagram: placeholder for now — see open questions below.

### `12_` — not yet written

Planned: design constraints imposed by the core methods (LLM eval, web fetching, local
file storage). Not implementation detail — the methods justify the architecture.

---

## Open questions

### 1. Candidate state model

We identified three axes that together drive loop decisions:

- **`info_level`**: `seed` → `partial` → `rich`
- **`user_verdict`**: `discard` / `skip` / `bof` / `interesting` / `very_interesting`
- **`inferred_verdict`**: same scale, LLM-computed from enriched data + user profile

The loop decision (enrich more / surface / stop) is a function of all three:

| `info_level` | `inferred` | `user_verdict` | → action |
| ------------ | ---------- | -------------- | -------- |
| seed         | any        | any            | → enrich |
| partial      | discard    | any            | → stop |
| partial      | interesting | any           | → enrich more |
| partial      | interesting | any           | → surface (if novelty trigger) |
| rich         | interesting | any           | → surface (force user verdict) |
| rich         | any        | discard        | → stop |
| rich         | any        | very_interesting | → shortlist |
| any          | any        | skip / bof     | → deprioritize, keep in pool |

The state diagram in `11_` is a placeholder until this model is resolved.

### 2. Curiosity / surprise score

To pick the top N candidates to surface or enrich next, you need a ranking. Options
discussed:

- **LLM outputs `surprise_potential`** during the eval step (essentially free — LLM
  is already reading the candidate). Absolute label, ranking derived by sorting.
- **Heuristic formula** from the known axes (info_level, inferred_verdict confidence,
  time since last surface). Cheap, transparent, no extra LLM call.
- **Embeddings** — surprise = distance from already-reviewed candidates. More principled,
  adds complexity and vector store dependency. Natural upgrade path if ranking quality
  becomes a problem.

### 3. ELO ranking

An unexplored idea: instead of absolute scoring, use pairwise comparisons (ELO). The
user makes binary choices ("which of these two looks more interesting?"). Advantages:
low cognitive load, no absolute scale needed, handles sparse feedback well, upsets are
strong profile signals. Open questions:

- Compare candidates directly, or against a reference ideal?
- Does ELO replace `user_verdict` or sit alongside it?
- Bootstrapping: initialize ELO from `inferred_verdict` as a prior?

### 4. Session definition

Deliberately left undefined. The loop has no fixed session boundary. Every operation
must be atomic — no half-enriched state. The system is always resumable. This needs
to be validated against the implementation as it grows.

---

## Next steps

- Resolve or defer the candidate state model (question 1) before finalizing `11_`.
- Write `12_` (design constraints from core methods).
- Decide whether ELO is in scope for the current iteration or a future idea to park.
