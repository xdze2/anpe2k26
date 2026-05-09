# Make node_id optional — drop _bootstrap sentinel

Date: 2026-05-09

## What changed

`node_id` is now `str | None` throughout the engine. Bootstrap passes `None`;
all per-node steps are unchanged.

### Motivation

The `_bootstrap` sentinel was a workaround for `node_id: str` being
non-optional, not a meaningful concept. Steps are all process-level objects —
`node_id` belongs to a *run*, not to a step. Bootstrap simply has no node to
attach to.

### Changes

- `Candidate.node_id: str | None` — `engine/base.py`
- `Item.node_id: str | None`, schema `TEXT` (was `TEXT NOT NULL`) — `engine/queue.py`
- `queue.put/mark_done/mark_error` signatures accept `str | None`
- `vault.store(node_id: str | None, ...)` — URI flipped to `{step}/{node_id}/...`;
  when `node_id` is None, segment omitted: `{step}/{ts}_{slug}.{ext}`
- `bootstrap_step.py` — `_NODE_ID = "_bootstrap"` deleted, both call sites use `None`
- `runner.py` — log path and `RunResult.node_id` updated for None
- `docs/specs/13_data_engine.md` — updated sentinel section and Vault URI convention

### Side effect: vault directory order flipped

Old: `user_vault/{node_id}/{step}/...`
New: `user_vault/{step}/{node_id}/...`

Existing `user_vault/` data is incompatible. Delete and rebuild from scratch.

## Status

81/81 tests pass.
