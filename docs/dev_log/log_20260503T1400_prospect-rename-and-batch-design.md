# 2026-05-03 — Rename enrich → prospect, design seed + batch

## What was done

### Rename: `enrich` → `prospect`

`anpe/enrich/` renamed to `anpe/prospect/`. All imports updated. CLI restructured
from a flat `anpe enrich <node_id>` command into a `prospect` group:

```
anpe prospect step <node_id>       # one fetch+summarize step (was: anpe enrich)
anpe prospect status <node_id>
anpe prospect summarize <node_id>
anpe prospect add_target <node_id> <tool> <keyword>
```

Rename note added to `docs/specs/31_poc_enrich_pipeline.md`.
All 15 tests pass.

### Rationale

"Enrich" describes a data operation. "Prospect" maps to the actual job-search
activity — building a dossier on companies worth approaching. Also reads more
coherently alongside `bootstrap`:

```
anpe bootstrap run     # generate listing from SIRENE
anpe prospect seed     # pick N companies, create nodes
anpe prospect run      # drive the fetch+summarize loop
```

## Next: seed + run-batch

### `anpe prospect seed`

Reads `user_data/company_listing.csv`, deduplicates by SIREN (the CSV is
per-établissement so one company may appear multiple times), skips SIRENs that
already have a node, picks N, and creates each node with an initial DDG target
queued (`"<nom_complet> <siren>"`).

```bash
anpe prospect seed --count 10
```

Options to consider: `--count N` (default 10), `--skip-existing` (default on).

### `anpe prospect run`

Drives the loop on all existing nodes that still have pending targets. For each
node, calls `enrich_step` repeatedly until the queue is empty or `--max-steps`
is reached, then moves to the next node.

```bash
anpe prospect run                  # loop until all queues empty
anpe prospect run --max-steps 5    # at most 5 steps per node
```

Order: nodes sorted by creation time (oldest first) to process them in seed order.
Stops on `empty_queue`; does not retry `blocked` or `fetch_error` automatically.

### Open question

Whether `seed` should immediately call `run` via `--run` flag, or whether keeping
them separate is better for dev inspection. Lean toward keeping them separate.
