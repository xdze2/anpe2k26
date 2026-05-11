# Step 10: list and view commands

Date: 2026-05-11

## What was done

### `anpe list`

Implemented in `cli.py`. Iterates `vault.root/nodes/*/` directly — no Step class
needed (read-only display). For each node:

- Loads `summarize_ddg_*.json` to check `status=not_relevant` (filtered unless
  `--keep-non-relevant`).
- Loads `eval_*.json` for score and fit.
- Loads `review_*.json` for reaction.

Renders a Rich table with columns: `node_id`, `score` (color-coded: green/yellow/
red/blue), `reaction`, `fit`.

Options:
- `--sort-field node_id|score|reaction` (default: `node_id`)
- `--nbr N` — cap rows shown
- `--keep-non-relevant` — include not_relevant nodes
- `--state reviewed|evaled|summarized|any` — filter by pipeline stage reached

### `anpe view <node_id>`

Resolves `summarize_ddg_*.json`, `fetch_siren_*.json`, and `eval_*.json` from the
node directory, then calls the existing `node_view()` from `steps/view.py` and
renders the result via `rich.Markdown`. Exits with error if the node directory or
summary file is missing.

## Current state

70 tests pass. Steps 1–10 done.

## Next

Step 11: delete old engine files (`queue.py`, `runner.py`, `sync_runner.py`,
`registry.py`, `base.py`).
