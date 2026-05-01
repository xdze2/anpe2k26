# 2026-05-01 — docs/ structure cleanup and spec writing

Picked up from the previous session's decision to reorganize `backlog/` into `docs/`.

The folder had the numbered flat files sitting alongside support folders (`dev_log/`, `references/`, `known_issues/`) — a mixed model. Fixed by pulling the numbered files into `docs/specs/`, which gives a clean split: specs in one folder, support material in the others.

Other changes:
- Dropped `01_repo_structure_decision.md` (overkill, the structure is self-evident)
- Fixed `enrichement` → `enrichment` typo in `42_enrichment_design_v2.md`
- Rewrote `00_process.md` — dropped stale paths, reframed "features" as "key parts", left dev log format open for freeform writing
- Added `docs/specs/README.md` as a file index with one-liner descriptions

The `inbox/` folder (pre-status ideas) was discussed but not created yet — deferred.

## Next

- Flesh out the empty spec files (`30_requirements.md`, `41_ia_agent_chat.md`)
- Create `inbox/` when needed
