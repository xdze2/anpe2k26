# 2026-05-05 — Data flow spec

Wrote `docs/specs/12_data_flow.md`, formalising the storage conventions that
emerged from the ddg+summarize work.

## Principles captured

Five core rules:

- **Text files only** — JSON, JSONL, Markdown; no database.
- **No overwrite for records** — raw fetch output, summarize results, and user
  profile snapshots are written once.
- **Views are derived and replaceable** — `summary.md` is a view, not a record;
  safe to overwrite because the authoritative copy is in `summarize/sum_*.json`.
- **No filename decoding** — paths are always carried as values in log entries;
  filenames are for legibility only.
- **Append-only log as queue, history, and cache** — `fetch.jsonl` is the single
  source of truth; queue state is derived by scanning it.
- **Version embedded in every result** — `summarize_version` in each `sum_*.json`
  enables staleness detection without external metadata.

## Key design decision: user profile versioning

The user profile can't follow the `summary.md` overwrite pattern because it will
be used as an input to the eval step. Inputs must be traceable.

Decision: each profile update writes a new `profile_<timestamp>.md`. The active
profile is the most recent by filename timestamp — no pointer file. Eval results
will record which profile file they used, enabling stale-eval detection when the
profile changes.

## Next

Start building the eval step: LLM scoring of candidates against the user profile.
Integration questions to think through:
- Where does eval fit in the pipeline state machine?
- Does it get its own `.jsonl` log, or does it extend `fetch.jsonl`?
- How does staleness propagate (profile update → re-eval)?
