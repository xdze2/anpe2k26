# 2026-05-02 — Summarize prompt tuning + siren formatter improvements

## Context

Tested the pipeline end-to-end on real companies (Smile, Thales, Sysnav).
Found two bugs and one missing feature in the summarize step.

## Problems found and fixed

### 1. `not_relevant` was filtering on job-search intent, not entity mismatch

The system prompt contained a hardcoded `_INTENT` ("small French tech companies doing
AI or software work"). The LLM used it to reject Thales — correct company, wrong profile.

Fix: dropped `_INTENT` entirely. `not_relevant` now means "this data is about a different
entity" (e.g. dictionary results for "SMILE"). The pipeline now also enqueues `new_targets`
even on `not_relevant`, so the LLM can propose a refined DDG query to retry.

### 2. DDG results are snippets — LLM wasn't proposing follow-up URLs

For Sysnav, the LLM summarized DDG snippets inline and returned `new_targets: []`.
The official site, LinkedIn, and Wikipedia were all present in the data but ignored.

Fix: prompt now explicitly says DDG results are snippets and instructs the LLM to
propose all found URLs in priority order: official site → Wikipedia → LinkedIn →
business news. Changed "keep the list short" to "propose all of them if found".

Result on Sysnav re-run:
- `https://www.sysnav.fr/`
- `https://fr.linkedin.com/company/sysnav`
- `https://entreprises.lefigaro.fr/...`
- `https://www.pappers.fr/...`

## Siren formatter improvements

- NAF code now decoded to label via `naf.py` `_load_csv_index()` (e.g. `62.02B —
  Conseil en systèmes et logiciels informatiques`)
- Headcount band decoded from raw code to human range (`"41"` → `"500-999 employees"`)
- Revenue and net result from `finances` dict (latest year)
- CEO extracted from `dirigeants` (first `personne physique` with "directeur" in title)
- DDG query gets sector suffix to reduce ambiguity: `" entreprise informatique"` for
  NAF section J, `" entreprise"` otherwise (fixes "SMILE" → dictionary results)
- Prompt capture file now includes full system prompt under `## System prompt` header

## Duration issue

Observed `duration_s: 51.65s` on the Sysnav DDG summarize step. Root cause is the
free-tier model on OpenRouter (`gpt-oss-20b:free`) being slow/rate-limited, not the
pipeline itself. Paid models (gpt-4o-mini, haiku) would bring this to ~2-5s.

## Next

- Domain blocklist before queuing `fetch` targets: pappers.fr, infogreffe.fr,
  societe.com, verif.com, gowork.fr, glassdoor.fr, jobteaser.com — these never
  add company intelligence, just waste a fetch+LLM call.
- Pipeline parallelism across nodes (multiple companies at once) — blocked on
  model latency being the real bottleneck for now.
- `fetch` tool implementation (currently targets queue up but nothing processes them).
</content>
</invoke>