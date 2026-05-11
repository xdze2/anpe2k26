# Implementation plan: one-command-per-step architecture

Each task is independently testable. Work in order — later tasks build on earlier ones.

## Done

- **cli.py cleanup (2026-05-11):** deleted old `cli.py` (stubs only), renamed `cli2.py` → `cli.py`,
  updated `pyproject.toml` entry point to `anpe.cli:cli`. `anpe --help` verified working.
- **Step 1 done (2026-05-11):** `engine/types.py` created with `FatalError`, `RetryableError`, `Log`, `Candidate`.
- **Step 2 done (2026-05-11):** `Vault.output_uri(node_id, step_name)` added. No `find_latest` — no migration needed, previous vault data deleted.
- **Step 3 done (2026-05-11):** `engine/run_step.py` created with `run_step` and `log_appender`. 5 tests pass.
- **Step 4 done (2026-05-11):** `BootstrapStep` rewritten (no Queue). `scan` checks `vault.exists("listing.jsonl")`. `work` writes directly to `vault.root / "listing.jsonl"`. `anpe bootstrap [--overwrite]` wired in `cli.py`. CLI stubs cleaned up. 5 tests pass.
- **Vault refactor (2026-05-11):** `Vault.store()` replaced by `Vault.write(uri, data, log=None)` — caller supplies the URI directly. `store()` was generating timestamped paths with a redundant `slug` param; now callers use `vault.output_uri()` to build the URI and pass it to `write()`. Bootstrap and all ported steps updated. `Candidate.skip` field added so `scan()` can yield already-done items; `run_step` counts them as skipped without calling `work()`. `skipped=1` now correctly reported on second `anpe bootstrap` run.

---

## Step 3 — shared CLI loop helper `run_step`

Create `anpe/engine/run_step.py`:

```python
def run_step(step, vault, do_max, **flags) -> tuple[int, int]:
    """Run scan→work loop. Returns (ran, skipped)."""
    candidates = step.scan(vault, **flags)
    if do_max is not None:
        candidates = itertools.islice(candidates, do_max)
    ran = skipped = 0
    for candidate in candidates:
        with log_appender(vault, candidate.node_id) as log:
            try:
                step.work(candidate.args, vault, log)
                ran += 1
            except FatalError as e:
                log(f"fatal: {e}")
                skipped += 1
            except RetryableError as e:
                log(f"retry: {e}")
                skipped += 1
    return ran, skipped
```

`log_appender` opens (appends to) `user_vault/nodes/<node_id>/node.log` or
`user_vault/node.log` for process-level steps.

**Test:** pass a mock step with a `scan()` that yields two candidates and a `work()`
that records calls. Verify counts and that the log file is created.

---

## Step 4 — port `bootstrap`

Rewrite `BootstrapStep.scan` to replace `queue.is_done(...)` with
`vault.exists("listing.jsonl")`. Drop `refresh` arg (use `--overwrite` flag instead).

`work` writes directly to `vault.root / "listing.jsonl"` (overwrite, not
content-addressed).

Wire up `anpe bootstrap [--overwrite]` in `cli2.py`.

**Test:** `scan` returns no candidate when `listing.jsonl` exists and `overwrite=False`;
returns one candidate otherwise.

---

## Step 5 — port `fetch_siren` end-to-end

Rewrite `FetchSirenStep` so it no longer touches `Queue`:

- `scan(vault, overwrite, **_)`: reads `listing.jsonl` directly from
  `vault.root / "listing.jsonl"`; for each row checks
  `vault.exists(vault.output_uri(node_id, self.name))`; yields `Candidate` only when
  output is missing (or `overwrite=True`).
- `work(args, vault, log)`: fetch siren, write to
  `vault.output_uri(node_id, self.name)` using `vault.root / uri` directly (not
  `vault.store()`, which was write-once). Drop the `async` — make it a plain sync
  method.

Wire up `anpe fetch_siren [--do-max N] [--overwrite]` in `cli2.py` using `run_step`.

**Test:**
1. `scan` yields nodes from listing, skips those with existing output files.
2. `work` writes a file; re-running `scan` with `overwrite=False` skips it.
3. CLI smoke test: run `anpe fetch_siren --do-max 0` and check it prints a summary
   line without errors.

---

## Step 6 — port `fetch_ddg`

Same pattern as `fetch_siren`. `scan` globs `nodes/*/` for nodes that have a
`fetch_siren_*.json` but no `fetch_ddg_*.json` (or use `vault.output_uri`).

Wire up `anpe fetch_ddg [--do-max N] [--overwrite]` in `cli2.py`.

**Test:** scan yields nodes that have siren but no ddg output; skips the rest.

---

## Step 7 — port `summarize_ddg`

`scan` finds nodes with `fetch_ddg` output but no `summarize_ddg` output. Loads
siren + ddg files using `vault.find_latest`. Calls `summarize_fn.ddg_summarize`.

Wire up `anpe summarize_ddg [--do-max N] [--overwrite]` in `cli2.py`.

**Test:** scan skips node that already has summary; yields node that doesn't.

---

## Step 8 — port `llm_eval`

`scan` finds nodes with summarize output and `status == "ok"` (unless
`skip_non_relevant=False`) but no eval output.

Wire up `anpe llm_eval [--overwrite] [--skip-non-relevant]` in `cli2.py`.

**Test:** scan skips `not_relevant` nodes when flag is set; yields `ok` nodes.

---

## Step 9 — port `review`

`scan` finds nodes with summarize output but no user-review output. Supports
`--random` (shuffle before `islice`).

`work` is interactive: renders the node card via `view.py`, calls `questionary.select`,
writes `user_review_<node_id[:8]>.json`.

Wire up `anpe review [--do-max N] [--random] [--skip-non-relevant] [--overwrite]`
in `cli2.py`.

**Test:** `scan` skips already-reviewed nodes. `work` is hard to unit-test; manual
smoke test suffices.

---

## Step 10 — add `list` and `view` commands to `cli2.py`

Both are read-only display commands already partially designed in `steps/view.py`.
Wire them up using `vault.find_latest` to locate artifacts per node.

`anpe list [--skip-non-relevant] [--nbr N] [--sort-field FIELD] [--state STATE]`
`anpe view <node_id>`

**Test:** run against the real vault and verify no crash.

---

## Step 11 — delete old engine files and old `cli.py`

Remove:
- `engine/queue.py`
- `engine/runner.py`
- `engine/sync_runner.py`
- `engine/registry.py`
- `engine/base.py`
- `cli.py` (replaced by `cli2.py`)

No `pyproject.toml` change needed — entry point already points to `cli:cli`.

**Test:** `uv run anpe --help` works; all remaining tests pass.

---

## Step 12 — update tests

- Delete `test_engine_queue.py` and `test_engine_runner.py`.
- Rewrite `test_engine_steps.py` to test new `scan()` signatures directly (no Queue
  mock needed — just a temp-dir Vault and fixture files).
- Verify `uv run pytest` passes clean.
