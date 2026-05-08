# Add fetch_siren step; rewire fetch_ddg and summarize_ddg — 2026-05-08

## What was done

### Root cause

The engine pipeline was missing a `fetch_siren` step. `FetchDdgStep` was
reading directly from the bootstrap listing and using `nom_complet` as the DDG
search query — bypassing the SIREN registry entirely. This meant the commercial
name (better for search) and NAF section (needed to pick the right suffix) were
never used.

### New pipeline chain

```
bootstrap → fetch_siren → fetch_ddg → summarize_ddg → eval
```

All steps source from the previous step's queue `done` events. No step reads
from the filesystem or the bootstrap listing directly (except `fetch_siren`,
which sources from the bootstrap listing in the vault).

### `fetch_siren` step (new)

**`anpe/engine/steps/fetch_siren.py`**

- Scans the latest bootstrap listing from the vault (same as the old
  `FetchDdgStep` did).
- One candidate per company, suppressed with `queue.is_done()`.
- `work()` calls `siren_fetch(siren_number)`, stores raw JSON in vault.
- Args: `{node_id, tool, target, listing_uri}` (target = SIREN number).
- Outputs: `{raw_uri, siren}`.

### `fetch_ddg` step (rewritten)

**`anpe/engine/steps/fetch_ddg.py`**

- `scan()` now queries `fetch_siren` done events instead of the bootstrap
  listing.
- For each done event, loads the siren raw JSON from the vault to derive the
  DDG search query: commercial name (`nom_commercial` or `nom_complet`) plus a
  NAF-section suffix (`" entreprise informatique"` for section J, `" entreprise"`
  otherwise).
- Args: `{node_id, tool, target, siren_uri}`.

### `summarize_ddg` step (rewritten)

**`anpe/engine/steps/summarize_ddg.py`**

- `scan()` now queries `fetch_ddg` done events. Retrieves `siren_uri` from the
  put args of each `fetch_ddg` item (stored in the queue at put time).
- All old filesystem scanning (`NODES_DIR`, `fetch.jsonl`, `_has_summary_for`)
  is gone. Suppression uses `queue.is_done()`.
- `work()` loads both `raw_ddg_uri` and `siren_uri` from the vault. Builds
  `company_profile` from the siren data: name, SIREN, NAF code + label
  (via `_load_csv_index`), city, headcount band.
- Args: `{node_id, raw_ddg_uri, siren_uri}`.

### `siren_summarize` deleted

**`anpe/prospect/fetch/siren.py`** — `siren_summarize` and
`SIREN_SUMMARIZE_VERSION` removed. The DDG target derivation logic it contained
(commercial name + NAF suffix) now lives in `fetch_ddg._ddg_target()`. The NAF
label lookup is used directly in `summarize_ddg._fmt_company_profile()`.

**`anpe/prospect/registry.py`** — `siren` entry removed from `FETCH_TOOLS`.

### Registry

**`anpe/engine/registry.py`** — `FetchSirenStep` registered between
`BootstrapStep` and `FetchDdgStep`.

### Tests

**`tests/test_engine_steps.py`** — `TestFetchSirenStepScan` added (6 tests).
`TestFetchDdgStepScan` rewritten around `fetch_siren` done events. 
`TestSummarizeDdgStepScan` rewritten around `fetch_ddg` done events (no more
`NODES_DIR` monkeypatching).

**`tests/test_engine_runner.py`** — stale `summarize_ddg.NODES_DIR` monkeypatch
removed. `test_scan_produces_json_lines` updated to seed a `fetch_siren` done
event instead of a bootstrap listing.

## Status

- 37 engine tests pass (25 step + 12 runner).

## Next

- Fix `EvalStep.scan()` — still reads old-pipeline `fetch.jsonl` and
  `summarize/` dirs; needs to source from `summarize_ddg` done events.
- Run a full end-to-end: `anpe step fetch_siren` + `anpe step fetch_ddg` +
  `anpe step summarize_ddg` to verify the connected pipeline works on real data.
- Eventually delete old pipeline code (`pipeline.py`, `eval_pipeline.py`,
  `summarize.py`, `prospect/fetch/` remnants, old CLI commands).
