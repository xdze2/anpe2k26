# `fetch_ddg` scan via queue+vault; explicit env args — 2026-05-08

## What was done

### Root cause of `summarize_ddg` not appearing in `anpe jobs status`

`SummarizeDdgStep.scan()` was reading per-node `fetch.jsonl` files in
`user_data/nodes/` to find completed fetch runs. But the engine writes its
done events to the SQLite queue in `user_vault/queue.db` — the two systems
were completely disconnected. The step never saw any fetch results, so it
emitted zero candidates.

The same disconnect affected `FetchDdgStep._scan_listing()`, which read the
bootstrap listing directly from the filesystem path instead of going through
`vault.load()`.

### `FetchDdgStep` — rewritten `scan()`

**`anpe/engine/steps/fetch_ddg.py`**

- `_scan_listing()` now calls `vault.load(listing_uri)` instead of constructing
  a filesystem path from `USER_VAULT_DIR / listing_uri`. The listing URI comes
  from the queue (already correct since the previous session).
- Suppression of already-done nodes now uses `queue.is_done()` instead of
  globbing `user_data/nodes/` and `user_vault/` for existing directories.
- `_scan_followups()` deleted. This method read old `fetch.jsonl` files in
  `user_data/` (old-pipeline format). Follow-up targets emitted by
  `summarize_ddg` will instead be `put()` into the queue as new `fetch_ddg`
  candidates — discovered naturally on the next `anpe scan fetch_ddg`.

### `scan(queue, vault, **filter_flags)` — explicit environment args

All four step `scan()` methods now receive both `queue` and `vault` as
positional arguments. The rationale matches the existing `queue` argument:
both are database connections with a lifecycle managed by the caller — not
module-level singletons. Passing them explicitly keeps the dependency visible
and lets tests inject isolated instances without monkeypatching globals.

Steps that don't currently use `vault` in scan (`bootstrap`, `summarize_ddg`,
`eval`) accept it as `_vault` for protocol conformance.

**`anpe/engine/steps/base.py`** — `Step` protocol updated:
`scan(self, queue, vault, **filter_flags)`.

**`anpe/cli.py`** — `cmd_scan` and `cmd_step` both open `Queue()` and
`Vault()` before calling `scan()`.

### Spec update

**`docs/specs/13_data_engine.md`** — "What each step declares" section updated
to reflect the actual `scan(queue, vault, **filter_flags) -> list[Candidate]`
signature with a note on why both args are explicit.

### Test updates

**`tests/test_engine_steps.py`** — `TestFetchDdgStepScan` rewritten around
the queue+vault fixture. Old tests exercised `_scan_followups()` (now deleted)
and filesystem path construction (now gone). New tests:
- `test_empty_when_no_bootstrap` — no bootstrap done → no candidates.
- `test_bootstrap_not_done_returns_empty` — bootstrap put but not done → no candidates.
- `test_listing_emits_candidate` — completed bootstrap → candidate with correct target and listing_uri.
- `test_already_done_not_a_candidate` — after a completed fetch_ddg run, same company not re-emitted.
- `test_count_caps_candidates` — `count=3` caps a 5-company listing.
- `test_multiple_companies_all_emitted` — 3 companies → 3 candidates.

All `scan()` calls in step tests updated to pass `self.vault`.

**`tests/test_engine_runner.py`** — `patch_nodes` fixture no longer patches
`fetch_ddg.NODES_DIR` or `fetch_ddg.USER_VAULT_DIR` (both removed).
`test_scan_produces_json_lines` rewritten to seed the queue+vault with a
completed bootstrap listing instead of writing a `fetch.jsonl` file.

## Status

- 35 engine tests pass (23 step + 12 runner).

## Next

- Fix `SummarizeDdgStep.scan()` — still reads `fetch.jsonl` directly, needs
  to query the queue for completed `fetch_ddg` done events instead.
- Fix `EvalStep.scan()` — same pattern, reads `fetch.jsonl` and `summarize/`
  dirs directly.
- Once both are fixed, run a full `anpe step fetch_ddg` + `anpe step summarize_ddg`
  end-to-end to verify the pipeline is connected.
