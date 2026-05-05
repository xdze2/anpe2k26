# 2026-05-05 — Eval step implementation

Implemented the full LLM eval pipeline as specified in `50_llm_eval_step.md`.

## What was built

**`anpe/profile.py` — profile storage refactor**

Replaced the single `profile.md` with timestamped snapshots (`profile_<ts>.md`).
`active_profile_file()` returns the most recent file by filename sort.
`write_profile_snapshot()` writes a new immutable file on each update.
`agent.py` updated to use `write_profile_snapshot`.

**`anpe/prospect/eval.py` — LLM eval module**

Pydantic-AI agent using `mistral-small-2603` (same model as summarize).
`EvalResult` model: `score`, `fit`, `dealbreakers`, `uncertainty`.
`EVAL_VERSION` hash (system prompt + model name) — same staleness mechanism as
`SUMMARIZE_VERSION`. `llm_eval(summary, profile) -> EvalResult` async function.

**`anpe/node_dir.py` — eval storage**

Added `eval_queue.jsonl` and `eval_results/` per node.
State = last event in the file (no uid — the queue is linear, one node one slot).
`append_eval_put`, `mark_eval_done`, `mark_eval_error`, `pop_eval_pending`,
`save_eval_result`, `is_eval_stale`.

**`anpe/prospect/eval_pipeline.py` — eval runner**

`eval_step(node_id) -> EvalStepLog` and `run_eval_batch(node_ids, budget)`,
mirroring the shape of `pipeline.py` / `run_batch`.

**`anpe/prospect/pipeline.py` — wiring**

After `status == "ok"` summarize, `_run_process` appends an eval `put` to
`eval_queue.jsonl`. Skipped for `not_relevant` and `no_data`. Skipped silently
if no profile file exists yet.

**`anpe/cli.py` — two new commands**

`anpe prospect eval` — processes the eval queue, same `-n` / `--until-done`
flags as `prospect run`.
`anpe prospect reeval` — syncs the eval queue: enqueues any summarized node
that has no current eval (never-enqueued or stale). Uses `get_latest_sum_file()`
to look up the correct `sum_file` from `fetch.jsonl` rather than the eval queue,
so it works even when `eval_queue.jsonl` does not exist yet.

## Design decisions made during implementation

**No uid in eval_queue.jsonl.** The fetch pipeline needs uids to correlate
`put → fetch_done → summarize_done` across parallel targets. Eval has no
branching — one node, one slot, linear sequence. State = last event.
A reeval is just a new `put` after `eval_done`; the log tells the story.
`reeval` event type dropped; `put` with a newer `profile_file` is sufficient.

**`enrich` score left as a dead-end for now.** The score is written and
displayed, but nothing re-queues fetch targets automatically. The loop will be
closed later when the full pipeline interaction is better understood.

**Eval only fires on `status == "ok"`.** `no_data` and `not_relevant`
summarize results do not enqueue eval. Filtering happens in `_run_process`
before the eval queue is touched.

**`reeval` covers both never-enqueued and stale nodes.** Originally `reeval`
only handled the stale case (reading `sum_file` from the eval queue). Nodes
summarized before the eval step existed had no eval queue and were silently
skipped. Fixed by reading `sum_file` from `fetch.jsonl` via
`get_latest_sum_file()` instead — making `reeval` the single command to sync
the eval queue with the current state of the world.

## Tests

60 tests, all passing. New test files:
- `tests/test_profile.py` (8 tests)
- `tests/test_eval.py` (3 tests)
- `tests/test_node_dir_eval.py` (12 tests)
- `tests/test_eval_pipeline.py` (5 tests)
- `tests/test_pipeline_eval_wiring.py` (3 tests)
- `tests/test_cli_eval.py` (7 tests — includes backfill case)

## Next

- `anpe prospect list` should show eval score alongside fetch state.
- `anpe prospect review` should surface eval score + fit during the review session.
- Close the `enrich` loop: when score is `enrich`, re-queue fetch targets.
- `anpe profile update` live implementation (currently `--dry-run` only).
