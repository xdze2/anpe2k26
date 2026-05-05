---
status: current
---

# Data flow design

This document describes the storage and state-machine conventions used by the
enrichment pipeline. The goal is to capture the principles behind the design,
not restate what the code already shows.

## Core principles

**Text files only.** All persistent state is plain text: JSON, JSONL, Markdown.
No database, no binary formats. Any file can be opened, inspected, or edited with
standard tools. Serialisation bugs are readable.
Data vault in `user_data/` dir, private git repo.

**No overwrite for records.** Raw fetch output, summarize results, and user profile
snapshots are written once and never modified — they are records.

**Views are derived and replaceable.** A small number of files are overwritable
_views_: derived from records, kept for convenient access, not authoritative.
`summary.md` is a view (its content is duplicated from the latest `sum_*.json`).
When a view is used as input to a later pipeline step, it must instead be a
timestamped snapshot so the link can be recorded — see the user profile section below.

**No filename decoding.** File paths are always carried as values inside log entries.
Nothing infers meaning from a filename. This means filenames can include human-readable
slugs for legibility without creating a dependency on their format.

**Append-only log as queue, history, and cache.** `fetch.jsonl` is the single source
of truth for what has been done, what is pending, and what failed. Appending a new
event never invalidates prior events — the log is the audit trail. Queue state is
derived by scanning the log; there is no separate queue structure.

**Version embedded in every result; inputs logged alongside outputs.** Each
`sum_*.json` file records the `summarize_version` (a hash of prompt + model +
blacklist) and the `raw_file` it was derived from. When the version changes, the
pipeline can detect stale results and re-queue them without touching the raw data.
The full prompt is also saved to disk (`prompt_*.txt`) so LLM calls are reproducible
and auditable.

---

## Node directory layout

Each candidate company is a _node_: a directory under `user_data/nodes/<node_id>/`.

```
nodes/<node_id>/
  fetch.jsonl          ← append-only event log (queue + history)
  summary.md           ← view: current summary (YAML frontmatter + markdown body)
  raw_data/            ← one file per completed fetch, never overwritten
  summarize/           ← one result file per summarize run, never overwritten
  reviews.jsonl        ← user reactions, append-only
```

### fetch.jsonl — event types

| event                                                 | meaning                                                      |
| ----------------------------------------------------- | ------------------------------------------------------------ |
| `put`                                                 | target enqueued; carries `uid`, `tool`, `target`             |
| `fetch_done`                                          | raw data saved; carries `raw_file` path                      |
| `fetch_error` / `not_found` / `blocked` / `retryable` | fetch failed                                                 |
| `summarize_done`                                      | result saved; carries `result_file` path                     |
| `summarize_not_relevant`                              | company out of scope or wrong entity                         |
| `summarize_error`                                     | LLM call failed; retryable                                   |
| `resummarize`                                         | re-queue for summarize without re-fetching; carries `reason` |

State for a uid is the _last_ event seen for that uid. `pop_pending` returns the
first uid whose last event is `put`, `summarize_error`, or `resummarize`.

### raw_data/ — naming

```
raw_<tool>_<slug>_<timestamp>.<ext>
```

Filename is for legibility only. The canonical reference is the `raw_file` field
in the `fetch_done` event.

### summarize/ — naming

```
sum_<tool>_<slug>_<status>_<timestamp>.json
prompt_<tool>_<slug>_<status>_<timestamp>.txt
```

Each `sum_*.json` contains: `fetch_uid`, `raw_file`, `model`, `summarize_version`,
`status`, `summary`, `new_targets`, `duration_s`. The `prompt_*.txt` companion
stores the full prompt sent to the LLM.

---

## State machine (per uid)

```
put ──fetch──► fetch_done ──summarize──► summarize_done      (ok | no_data)
     │                   │                   └─ enqueues new_targets as put events
     │                   └────────────► summarize_not_relevant
     ▼
fetch_error | not_found | blocked | retryable   [terminal — manual retry only]

summarize_error  [retryable — pop_pending picks it up again; fetch is skipped]
resummarize      [retryable — same as summarize_error but triggered by version change]
```

`resummarize` is the mechanism for invalidating summaries without discarding raw
data. When `summarize_version` in a `sum_*.json` no longer matches the tool's
current version constant, the pipeline appends a `resummarize` event. The next run
skips the fetch step (raw file is already on disk) and re-runs summarize only.

---

## Version and staleness

`SUMMARIZE_VERSION` is a short SHA-1 hash over the system prompt, model name, and
blacklist contents. Any change to these inputs changes the hash, which automatically
invalidates existing summaries when `get_stale_summarize_uids` scans the node.

Each `FetchTool` in `registry.py` declares its own `version` string because tools
with deterministic summarization (e.g. `siren`) have their own versioning logic
independent of the LLM prompt hash.

The version is written into every `sum_*.json` at creation time. Staleness is
detected by comparing the stored version to the current constant — no external
metadata needed.

---

## Views vs records

**`summary.md`** is an overwritable view of the node's current state: YAML frontmatter
(structured fields from SIREN: name, siren, naf, city, headcount) plus a markdown body
produced by the LLM. Its body is a duplicate of the `summary` field in the latest
`sum_*.json`. The authoritative history is in the `summarize/` directory. `summary.md`
is the read surface for the user and for the LLM prompt on the next enrichment cycle.

`summary.md` is not suitable as a traceable pipeline input. If a later step (e.g. eval)
reads the summary, it should link to the specific `sum_*.json` file it used, not to
`summary.md`.

---

## User profile

The user profile follows the no-overwrite rule: each update writes a new timestamped
file. The most recent file by timestamp is the active profile.

```
user_data/
  profile_20260505T1200.md   ← snapshot, never modified
  profile_20260506T0900.md   ← newer snapshot, currently active
```

This matters because the profile is an input to the eval step. An eval result must
record which profile file it used — the same way `sum_*.json` records `raw_file`.
This makes it possible to detect stale evals when the profile has been updated since
they were run.

The active profile is resolved at runtime by taking the latest by filename timestamp,
not by a pointer file.
