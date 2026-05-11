# Pivot: drop the data engine, one command per step

Date: 2026-05-11

## Context

The current architecture routes every step through a shared engine:
`scan()` → `Queue.put()` → `Runner.claim()` → `work()` → `Queue.mark_done()`.
The SQLite queue (`queue.db`) was designed to support concurrency, crash recovery,
and cross-run staleness tracking.

In practice the complexity exceeded the value: two runner classes, 700 lines of
engine code, a content-addressed uid scheme, and frequent queue-repair sessions
(flush → re-put cycles, dedup fixes, asyncio/sync routing). The `SyncRunner`
emergency added in the last session to fix `ReviewStep` is a symptom.

## The pivot

Each step becomes a self-contained CLI command with a direct `scan | work` loop.
No shared runner, no SQLite queue.

**What we keep:**

- `scan()` / `work()` method split — scan builds the candidate list by reading vault
  files, work executes one item. Clean separation, independently testable.
- `Vault` — the filesystem artifact store with content-addressed URIs. This is the
  new source of truth for "done": if the output file exists, the item is done.
- `FatalError` / `RetryableError` — still useful to distinguish permanent failures
  from transient ones inside `work()`.
- `rate_gate` — per-step rate limiting (DDG, Mistral).
- One log file per node, append-only. `work()` appends to
  `user_vault/nodes/<node_id>/node.log` instead of writing a uid-scoped `.log` file
  per run.
- API disk cache under `cache_data/` — unchanged.

**What we remove:**

- `engine/queue.py` — the SQLite event log, `put/claim/mark_done/mark_error`, all
  queue repair tooling.
- `engine/runner.py` — async multi-worker runner.
- `engine/sync_runner.py` — serial sync runner added as a workaround.
- `engine/registry.py` — step registry.
- `engine/base.py` — `Candidate`, `AsyncStep`, `SyncStep` protocols; keep only
  `FatalError`, `RetryableError`, `Log` (move to a small `engine/types.py` or
  inline in `steps/`).
- `anpe jobs` CLI subcommand and all queue inspection commands.

**What we gain:**

- Crash recovery and resumability still work: every `work()` call writes its output
  file immediately. Re-running the command skips nodes that already have output.
- No accumulation of timestamped artifact files per re-run — one output file per
  node per step (overwrite on `--overwrite`).
- `scan()` reads vault files directly instead of querying `done_events()`. The
  staleness check is `vault.exists(output_path)` — equivalent to the makefile
  model. Input-change detection (re-run when input is newer than output) can be
  added later using file mtimes, exactly like make.
- The CLI loop is trivial (~10 lines) and identical for every step.

**What we lose:**

- Per-run history: no record of previous outputs for the same node. The latest
  output file is the only copy. Acceptable — the vault was write-once as a
  debugging aid, not a requirement.
- `anpe jobs stack <step>` — pending queue inspection. Replaced by: re-running the
  command dry-run style (scan prints candidates without running work), or just
  running normally with `--do-max 0`.

## New spec

See `docs/specs/12_steps.md` for the full per-step reference: description, CLI
args, inputs/outputs, external resources, methods, and output fields.

## Implementation path

### 1. New thin engine (`engine/types.py`)

```python
FatalError(Exception)
RetryableError(Exception)
Log = Callable[[str], None]
```

Keep `Vault` in `engine/vault.py` unchanged.
Keep `rate_gate.py` unchanged.

### 2. Rewrite `scan()` in each step

Replace `queue.is_done(...)` with `vault.exists(output_uri)`.
Replace `queue.done_events(upstream_step)` with a vault directory scan or a small
helper that reads `listing.jsonl` / iterates `nodes/*/`.

Scan signature becomes:

```python
def scan(self, vault: Vault, **flags) -> Iterator[Candidate]
```

Where `Candidate` is a simple dataclass: `node_id`, `args`, nothing else.

### 3. Shared CLI loop helper

`scan()` is the sole decision point: it checks input existence, output existence,
and (eventually) mtimes. The loop just consumes what scan yields.

```python
def run_step(step, vault, do_max, **flags):
    for candidate in itertools.islice(step.scan(vault, **flags), do_max or None):
        with log_appender(vault, candidate.node_id) as log:
            try:
                step.work(candidate.args, vault, log)
            except FatalError as e:
                log(f"fatal: {e}")
            except RetryableError as e:
                log(f"retry: {e}")
```

`overwrite`, future mtime checks, and any other filter flags are passed through
`**flags` into `scan()`. `Candidate` does not need an `output_uri` field — scan
has already decided the item needs running before yielding it.

### 4. Rewrite `cli.py` as `cli2.py`

Register each step command. Each command instantiates its step class, calls
`run_step(...)`, prints a summary line. Replace the old `cli.py` entirely.

### 5. Delete engine files

```
engine/queue.py
engine/runner.py
engine/sync_runner.py
engine/registry.py
engine/base.py       (replaced by engine/types.py)
```

### 6. Update tests

Tests that use `TestQueue` / `Runner` are deleted or rewritten against the new
`scan()` signature. Step `work()` tests are unaffected — they call `work()`
directly and don't touch the engine.

## Order of execution

1. Write `engine/types.py`, keep vault + rate_gate.
2. Port one step end-to-end (`fetch_siren` is the simplest): new scan, new CLI
   command, log appender.
3. Verify manually: run command, check file written, re-run skips it.
4. Port remaining steps in pipeline order: bootstrap → fetch_ddg → summarize_ddg
   → llm_eval → review.
5. Delete old engine files and old `cli.py`.
6. Update tests.

## Progress

See `todo.md` for the detailed step-by-step plan.

**2026-05-11 — No migration needed:** previous vault data deleted; all steps will
be re-run from scratch. `find_latest` helper dropped from Step 2 — `output_uri` is
the only addition to `Vault`.

**2026-05-11 — CLI cleanup done:**
Deleted old `cli.py` (it was stubs only, no real code), renamed `cli2.py` → `cli.py`,
updated `pyproject.toml` entry point from `anpe.cli:run` to `anpe.cli:cli`.
`anpe --help` verified working. Bootstrap order in the plan corrected: `bootstrap`
must run before `fetch_siren` since it produces `listing.jsonl`.
