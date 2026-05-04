# 2026-05-04 — Pipeline spec, prospect list improvements, profile update prompt

## What was done

### `prospect list` display

- Company name (from frontmatter) replaces node_id as primary identifier
- Model/prompt_version tag dropped — same for all nodes, not useful in a list
- Last review reaction shown inline as dim green trailing string

### `anpe profile update --dry-run`

New command. Formats the profile-update prompt (reactions + 150-char summary
snippets) and prints it to stdout for copy-paste into a web AI. No LLM call.
See previous log entry for experiment results.

### `docs/specs/21_pipeline_overview.md` — new spec

Pipeline overview document with a Mermaid graph and per-step input/output
tables. Three visual layers in the graph:

- Pills (blue) — external inputs: company listing, Internet, user
- Rectangles (teal) — process steps; dashed border for LLM steps
- Parallelograms (amber) — data artifacts written to disk

Key design decisions captured in the spec:
- `sample` edges from listing→bootstrap and summaries→review make the funnel
  explicit — the core value is that the user reviews ~10% of the listing,
  not all of it
- `new` edges into `update_profile` — only reactions/summaries since last
  `updated_ts` are included
- User profile is input AND output of `update_profile` (self-referential update)
- User profile is intentionally NOT injected into `fetch_and_summarize` —
  summaries are objective, profile-agnostic. Separation means a profile update
  only invalidates scores, not summaries.

## Open / in progress

The spec still needs work — comments left inline in the file:

- Intro paragraph is a placeholder ("The enrichment pipeline...")
- "Each output should reference the input used" — traceability requirement not
  yet reflected in the step tables
- Bootstrap sampling is currently arbitrary (alphabetical) — to be designed
- `anpe prospect seed` command reference needs a note in the bootstrap section

## Design decisions recorded

### Summary versioning

`summary.md` is currently overwritten on each `llm_summarize` run. The
immutable result file (`summarize/sum_*.json`) preserves history, but
`reviews.jsonl` events have no `sum_id` — the link between a reaction and the
summary it was written against is lost after re-summarization.

Planned fix: `reviews.jsonl` events carry a `sum_id` referencing the result
file the user actually read. `summary.md` becomes a materialized view.
Migration cost is low now (29 reactions); expensive at 100+.

### Profile not injected into summarize

Decided explicitly: `fetch_and_summarize` does not receive `profile.md`.
Rationale: summaries should be reusable across profile versions. If profile
were injected, every profile update would invalidate all summaries and require
re-fetching. Scoring is the subjective layer; summarization is objective.

## Next

- Complete and clean up `docs/specs/21_pipeline_overview.md` (see inline comments)
- Implement summary versioning (`sum_id` in `reviews.jsonl`)
- Rewrite the `llm_summarize` prompt (structured header: type · domain · market)
- Populate `profile.md` manually from the Mistral Medium experiment output
- Implement `score(summary, profile)`
