# 2026-05-01 — Principles and requirements docs

## What changed

Wrote `docs/specs/20_principles.md` from scratch. The file existed as a dump of
copy-pasted notes and had no structure. Rewritten as a high-level design doc that sits
between the vision and the detailed design docs — narrative, not prescriptive. Sections:
data vault, enrichment loop, eval structure, information sources, dispatcher, triage,
agent modes.

Key decisions captured or clarified in the process:
- Company data lives in `companies/node<SIREN>/` (one directory per node, not one file).
  The SIREN is the only stable key.
- The summarization step has a second role: identifying the next target for information
  retrieval — not just describing what was found.
- "Match delta" and summarization are always relative to the user profile, not objective.
- Profile update strategy (full rewrite vs append) marked as `[TBD]` — not yet settled.

Also wrote `docs/specs/30_requirements.md` as a detailed imperative spec (MUST/SHOULD
style). Agreed during session that full detailed requirements is overkill for this
project — `20_principles.md` is the right level. `30_requirements.md` exists and is
accurate but is not the primary reference.

## Next

- `41_ia_agent_chat.md` is still empty — worth fleshing out (agent interaction model,
  tool list, system prompt structure).
- Profile update strategy (full rewrite vs append) is `[TBD]` in principles — needs a
  decision.
