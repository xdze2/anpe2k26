# 2026-05-01 — POC enrichment pipeline

## What changed

Reworked `docs/specs/42_enrichment_design_v2.md` — full rewrite to align with the
current principles doc. Main changes: node is now a directory (`node<SIREN>/`) instead
of a flat file, two JSONL files (`enrichment.jsonl` for history, `queue.jsonl` for
intent), hybrid `next_fetch_target` (fixed steps first, then LLM-proposed), eval
reduced to 3 layers with fetch status handled by the tool not the LLM.

Then stepped back: the full spec was getting too complex to build against. Decided to
start with a minimal POC instead.

Wrote `docs/specs/31_poc_enrich_pipeline.md` — the simplest version of the enrichment
loop that produces real output:
- Queue bootstrapped with SIRENE + DDG targets
- One LLM call per fetch: `llm_summarize(data, previous_summary)` → status + updated
  summary + next targets
- No user profile yet — hardcoded intent in the prompt for testing
- Storage: `summary.md` + `queue.jsonl` only, no audit log for now

## Next

Start coding the POC: fetch tools (SIRENE, DDG), `llm_summarize`, the loop.
