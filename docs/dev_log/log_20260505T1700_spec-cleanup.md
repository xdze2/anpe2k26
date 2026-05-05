# 2026-05-05 — Spec cleanup

Reorganised `docs/specs/` and fixed four issues spotted during a full top-to-bottom
read.

## Changes made

**README.md rebuilt.** The index listed seven files that no longer exist and was missing
all the new specs. Replaced with the actual file list.

**Cross-reference fix in `40_user_review_and_profile_update.md`.** "After profile update"
section referenced `34_llm_eval_step.md` — the file was renamed to `50_llm_eval_step.md`
during reorganisation.

**`14_pipeline_overview.md` — `update_profile` row flagged WIP.** The table said
`profile.md` was overwritten on each update, contradicting the immutable-snapshot
convention established in `12_data_flow.md`. Row updated to show `profile_<timestamp>.md`
with a WIP marker — the implementation still needs to be changed to match.

**`31_enrich_pipeline.md` — status changed from `done` to `active`.** The file contained
live TODOs (target extraction not working, `fetch_url` not implemented) inconsistent with
`done`.

---

## Design note: summary.md should not be a persistent file

Current state: `summary.md` is written to disk by `llm_summarize` and read as input by
later pipeline steps (eval prompt, review display).

Problem: `summary.md` is described as a view in `12_data_flow.md`, but it is treated as
a record in practice. The distinction matters:

- It is read by the eval step — making it a traceable input that should be pinned to a
  specific `sum_*.json`, not a floating file that silently changes under an in-flight eval.
- It is shown to the user during review — but the user should be seeing the output of the
  latest summarize run, not whatever was last written to disk.

Proposed direction: eliminate `summary.md` as a persistent file. Replace it with an
`anpe prospect show <node_id>` command that renders the node state on demand from
`fetch.jsonl` + the latest `sum_*.json`. The eval step already reads `sum_file`
directly (per `50_llm_eval_step.md`); the review command would do the same.

Benefits:
- No more view/record ambiguity — the authoritative copy is always `sum_*.json`.
- `reviews.jsonl` could carry `sum_id` to pin which version the user actually read,
  closing the traceability gap noted in `14_pipeline_overview.md`.
- One less file written per summarize run; directory stays clean.

The `summary.md` section in `14_pipeline_overview.md` and `12_data_flow.md` would need
updating once this is implemented.

## Next

- Update `12_data_flow.md` and `14_pipeline_overview.md` to reflect `summary.md` → on-demand view decision.
- Implement `anpe prospect show`.
- Fix `update_profile` storage to write timestamped snapshots (flagged WIP in `14_`).
