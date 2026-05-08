# Data engine — chunks 1, 2, 3 — 2026-05-08

## What was done

Implemented the first three chunks of the data engine spec (`docs/specs/13_data_engine.md`).
Everything lives under `anpe/engine/`. The existing pipeline (`pipeline.py`) is untouched.
Storage root is `user_vault/`, fully separate from `user_data/`.

### Chunk 1 — Vault (`anpe/engine/vault.py`)

Write-once artifact store backed by the filesystem. Two methods: `save(uri, data) -> str`
and `load(uri) -> bytes`. Raises `VaultWriteError` on overwrite — the invariant that makes
content-addressed URIs work. URI maps directly to `user_vault/{uri}` on disk.

### Chunk 2 — Queue (`anpe/engine/queue.py`)

SQLite append-only event log (`user_vault/queue.db`). Six-method interface:
`put`, `claim`, `mark_done`, `mark_error`, `pending`, `stale_claims`.

Key properties:
- `put` is idempotent: `uid = sha256(step + version + args)[:16]`. Same logical run
  twice → same uid → second insert is a no-op.
- `claim` is atomic: single write transaction, two concurrent workers cannot claim
  the same item.
- `error_retry` items re-appear in `pending()`; `error_abort` items do not.
- `stale_claims(older_than_s)` surfaces claimed-but-unfinished items for crash recovery.
- `put(force=True)` perturbs the uid with a nonce for deliberate re-runs.
- `pending()` and `stale_claims()` always read args from the original `put` event row
  (not from the `claimed` or `error_retry` rows, which have no args).

### Chunk 3 — Steps (`anpe/engine/steps/`)

`Candidate` dataclass and `Step` protocol in `base.py`.

Three concrete steps, each DDG-specific by name and by filtering logic:

- **`FetchDdgStep`** (`fetch_ddg.py`, `name = "fetch_ddg"`) — scans `fetch.jsonl` for
  pending/error DDG targets. Ignores siren and other tool slugs structurally.
- **`SummarizeDdgStep`** (`summarize_ddg.py`, `name = "summarize_ddg"`) — scans for
  DDG `fetch_done` entries with no summary at the current `SUMMARIZE_VERSION`. Filter
  flag: `naf_prefix=`.
- **`EvalStep`** (`eval.py`, `name = "eval"`) — scans for `(node, sum_uri, profile_uri)`
  triples with no matching eval at the current `EVAL_VERSION`. Filter flags: `min_score=`
  (discard < enrich < maybe < good), `exclude_reaction=`. Surfaces `score`, `reaction`,
  `naf` in `context` for downstream filtering.

Step naming convention: tool-specific steps carry the tool name (`fetch_ddg`,
`summarize_ddg`). A future `fetch_raw` or `fetch_siren` step would follow the same pattern.

`work()` bodies delegate to the existing fetch/summarize/eval logic — no LLM code was
rewritten.

### Tests

- `tests/test_engine_vault.py` — 6 tests
- `tests/test_engine_queue.py` — 16 tests
- `tests/test_engine_steps.py` — 23 tests

105 tests total, all passing.

## Next

Chunk 4: Runner + CLI wiring (`anpe scan`, `anpe put`, `anpe run`).
