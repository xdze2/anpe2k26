# 2026-04-30 — Repository documentation structure

## What we worked on

Discussed how to organize project documentation. The current `backlog/` folder had
grown to contain both spec documents and scratch notes with no clear structure.

## Why / context

As the project grows (discovery + enrichment pipeline now in design), it becomes
harder to know which docs are authoritative, which are drafts, and what the overall
product intent is. Also wanted a place for narrative build notes that git commits
don't capture.

## Decisions made

- Adopt a `docs/product/`, `docs/design/`, `docs/reference/` split (product = client
  concerns, design/reference = internal)
- Add `dev_log/` for narrative session notes (this file)
- Add `ideas/` as a zero-friction pre-spec scratchpad
- Feature specs use in-file frontmatter (`status: draft | active | done`) rather than
  folder-per-state — keeps things flat, grep-able
- Dev log filename format: `log_ISODATE_slug.md` with compact ISO datetime (e.g. `20260430T0030`)
- Deferred: `make status` Makefile target once file count warrants it

Full decision record: `backlog/repo_structure_decision.md`

## Dead ends

- Considered SDLC-style numbered phases (00_requirements, 10_design, …) — rejected
  because phase boundaries blur and it implies a waterfall progression that doesn't
  match how this project actually moves
- Considered folder-per-status for design docs (draft/, active/, done/) — rejected
  in favor of frontmatter, less git noise

## Next

- Reorganize `backlog/` into the new structure when convenient
- Write a short `docs/product/vision.md` (3-sentence product description) as the
  top-level orientation doc
