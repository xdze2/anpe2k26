# prospect show + summary.md removal — 2026-05-05

## What was done

### Removed `summary.md` as a persistent file

`summary.md` was serving two purposes that have since been superseded:
- **Structured data injection** via YAML frontmatter — no longer used.
- **Readable metadata header** (name, city, headcount, naf) — was hand-crafted
  by the SIREN summarizer into frontmatter; now rendered on demand from the raw
  SIREN JSON.

The authoritative data is in `sum_*.json` (summary body) and `raw_siren_*.json`
(metadata). `summary.md` was a redundant copy that could drift.

**Deleted from `NodeDir`:** `_summary_file`, `_split_frontmatter`,
`get_frontmatter`, `set_frontmatter`, `get_summary_body`, `save_summary`,
`_write_summary`.

**Added to `NodeDir`:**
- `get_latest_summary()` — reads `summary` field from the latest `sum_*.json`.
- `get_siren_meta()` — reads the latest `raw_siren_*.json` and returns
  `{name, city, naf, headcount, siren, category}`. Falls back to `{}` if no
  SIREN file exists (newly seeded nodes).
- `get_next_targets()` — moved here from a private helper in `review.py`;
  returns `new_targets` from the latest summarize result file.

**`SummarizeResult.frontmatter` field removed** from `types.py`.

**`siren_summarize` simplified** — was building frontmatter dict and injecting
it; now only proposes a DDG follow-up search. Version bumped `v2` → `v3`.
The SIREN metadata lives in the raw file and is read directly by `get_siren_meta()`.

**`seed.py`** — removed the `set_frontmatter` call at node creation (was
writing name+siren before the SIREN fetch ran; now redundant since
`get_siren_meta()` reads the raw file).

All callers updated: `pipeline.py`, `review.py`, `cli.py` (list + profile update).

### Added `prospect show <node_id>`

New CLI command: `uv run anpe prospect show <node_id>`.

Displays in order:
1. Header rule: name + city, headcount, naf, siren (from SIREN meta)
2. Full summary body (Rich Markdown, from latest `sum_*.json`)
3. Eval result: score, uncertainty, fit, dealbreakers (if available)
4. Next targets: full list from latest summarize result
5. User reaction (if any)

### `prospect review` now requires a DDG summary

Previously, nodes with only a SIREN summary (no DDG fetch done yet) could
appear in the review queue. Added `has_ddg_summarize_done()` to `NodeDir` and
updated `_nodes_to_review()` to use it. Nodes without a DDG summary are now
skipped — there is not enough information to usefully review them.

## Files changed

- `anpe/node_dir.py` — removed frontmatter methods, added `get_latest_summary`,
  `get_siren_meta`, `get_next_targets`, `has_ddg_summarize_done`
- `anpe/prospect/types.py` — removed `frontmatter` field
- `anpe/prospect/fetch/siren.py` — simplified, version v3
- `anpe/prospect/pipeline.py` — updated callers, removed `save_summary` /
  `set_frontmatter` calls
- `anpe/prospect/seed.py` — removed `set_frontmatter` call
- `anpe/prospect/review.py` — updated callers, removed `_get_next_targets` helper
- `anpe/cli.py` — added `prospect show`, updated list + profile update callers
- `tests/test_prospect_seed.py` — removed stale `NODES_DIR` monkeypatch on seed module
