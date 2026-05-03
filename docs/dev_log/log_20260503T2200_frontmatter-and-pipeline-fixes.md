# 2026-05-03 — frontmatter, pipeline fixes, state machine

## What was done

### Bug fix: `not_relevant` fan-out loop

`not_relevant` results were enqueuing the LLM's proposed retry queries.
Those retries also returned `not_relevant`, spawning more queries — unbounded.

Fix: `not_relevant` is now a dead end. New targets proposed by the LLM are
recorded in the result file for auditability but never enqueued.

### State machine diagram in `pipeline.py`

The valid per-uid transitions are now documented in the module docstring:

```
put ──fetch──► fetch_done ──summarize──► summarize_done  (ok | no_data)
     │                   │                   └─ enqueues new_targets
     │                   └────────────► summarize_done  (not_relevant)
     │                                      └─ no new_targets enqueued
     ▼
fetch_error | not_found | blocked | retryable   [terminal / manual retry]
```

### `summary.md` as single source of truth (frontmatter)

Registry data (SIREN, NAF, headcount, city, category) now lives in YAML
frontmatter in `summary.md` instead of a `## SIREN data` markdown block
in the body. The LLM only sees and writes the body — it never touches the
structured fields.

New `NodeDir` API: `get_frontmatter()`, `set_frontmatter()`,
`get_summary_body()`. `save_summary()` now preserves existing frontmatter
when overwriting the body.

`siren_process` returns fields via `EnrichResult.frontmatter` (new optional
field). The pipeline applies them via `node.set_frontmatter()`.

`seed_from_listing` writes initial `siren` + `name` frontmatter at node
creation time.

### Pipeline order fixed: siren → ddg → llm

Seed used to queue a DDG target directly (e.g. `"Acme SAS 123456789"`),
polluting queries with the SIREN number and skipping the registry fetch.

Now seed queues `siren` as the first target. `siren_process` enriches
frontmatter and proposes a clean DDG query as follow-up (e.g.
`"Acme SAS entreprise informatique"`). The company profile is fully
populated before the LLM ever runs.

### `company_profile` wired into production

`_run_process` now passes `_fmt_company_profile(node.get_frontmatter())`
to `llm_summarize`. The LLM receives name, NAF, category, headcount, city
as authoritative ground truth on every DDG/fetch call.

## Observed problem — LLM duplicates frontmatter data in the body

The system prompt says "do not repeat information already in the Company
profile block", but in practice the LLM still copies name, city, sector
into the summary body — especially when DDG results are thin and there is
little else to say.

Root cause hypothesis: when the only available signal is the company name
and sector (DDG returned snippets with no new facts), the model fills the
summary with what it knows, which is the company profile itself.

This is a prompt + evaluation problem, not a data problem. The body should
only contain web-sourced intelligence. If there is nothing new to say, the
right output is `no_data`, not a paraphrase of the frontmatter.

## Next

- Tighten the prompt: make the "do not repeat company profile" rule more
  explicit, and clarify that thin DDG results with no new facts should
  return `no_data` rather than a summary that restates registry data.
- Add an eval fixture for this case: DDG result that contains only the
  company name and sector → expected status `no_data`.
- Verdict system (`to_look_at / discarded / good / very_good`) stored in
  frontmatter — prerequisite for the agent feedback loop.
