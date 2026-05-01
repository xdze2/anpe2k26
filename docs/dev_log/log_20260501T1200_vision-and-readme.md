# 2026-05-01 — Vision rewrite and README cleanup

## What changed

Rewrote `docs/specs/10_vision.md` from sparse bullet-point notes into a proper vision document. The previous file had the right ideas but no narrative thread. New structure: problem → discovery mechanism → how it works → core ideas → why this project exists.

Key reformulations:
- "Census not a crawl" → reframed around *discovering what you don't know exists yet*: SIRENE as an external, systematic source capable of surprise, not just a filter on known companies.
- "Phase 1 / Phase 2" → reframed as **bootstrap** (initial seeds from SIRENE) + **refinement loops** (enrichment + profile updates repeating across sessions). More accurate to how the system actually works.
- Learning/side-project angle: added "learning by building" framing, moved to end of document.
- Dropped the default model mention from the tech stack section — belongs in config, not vision.

Updated `README.md`:
- Was: installation + usage + minimal project structure (3 files, already stale).
- Now: short quickstart, usage commands, accurate project structure (reflects `profile.py`, `tools/`, `data/`, `docs/`), links to specs for deeper reading.

Deleted `design_doc.md` from repo root. All content was either superseded by `docs/specs/40_design.md` and `41_ia_agent_chat.md`, or outdated (tools table reflected a pre-enrichment state, next steps already executed).

## Next

- Flesh out `30_requirements.md` and `41_ia_agent_chat.md` (still mostly empty)
