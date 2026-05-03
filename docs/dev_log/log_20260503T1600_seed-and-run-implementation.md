# 2026-05-03 — seed, run, and CLI polish

## What was done

### `anpe prospect seed`

New command that reads `user_data/company_listing.csv`, deduplicates by
node_id, filters out nodes that already exist, and creates up to `--count N`
new nodes (default 10), each with an initial DDG target `"<nom_complet> <siren>"`.

Node id format: `<slug>_<siren>` — deterministic, human-readable, collision-free.
`slugify()` uses `unicodedata.normalize("NFD")` to strip accents.

```bash
anpe prospect seed --count 5
```

### `add_target`: require existing node

Removed the implicit node creation from `add_target` (and from
`NodeDir.append_target` itself). Nodes are now only created via `seed`.
Typos in node_id now produce a clear error instead of silently creating
a new node.

### `anpe prospect run`

Batch pipeline runner. Two axes:

- **Which nodes**: explicit `NODE_ID...` list, `--all-nodes`, or default
  (all nodes when no IDs given).
- **How many steps**: `-n N` total step budget across all nodes (default 1,
  safe); `--until-done` to run until all queues empty (explicit opt-in).

Step budget is a **total** counter across all nodes, not per-node. The loop
is depth-first: finish one node's budget before moving to the next.

Stops the entire run immediately on `blocked` (DDG down = no point continuing).
`empty_queue` steps are silently skipped in output (no noise).

```bash
anpe prospect run                         # 1 step, all nodes
anpe prospect run -n 10                   # 10 steps total
anpe prospect run -n 5 node1 node2        # 5 steps on specific nodes
anpe prospect run --all-nodes -n 10
anpe prospect run --all-nodes --until-done
```

### CLI help formatting

Used `\b` marker in Click docstrings to prevent line-wrapping of example
blocks in `--help` output.

## Next

- `anpe prospect list` — overview of all nodes: pending targets, last status,
  whether a summary exists. Essential visibility before/after runs.
- Concurrent node processing (semaphore-limited) for faster batches.
- Faster/cheaper model for first DDG pass.
