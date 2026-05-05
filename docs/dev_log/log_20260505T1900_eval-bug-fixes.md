# Eval bug fixes — 2026-05-05

## Bugs fixed

### KeyError: 'sum_file' on eval_error retry

`pop_eval_pending` returned the raw `eval_error` event, which has no `sum_file`
key. Fixed by walking back through `eval_queue.jsonl` to return the most recent
`put` event when the last event is `eval_error`.

### Infinite loop on not_relevant nodes

A node with only a `not_relevant` summary (no `summary` field in the JSON) was
writing `eval_error` on each run, making it permanently retryable. Fixed by
writing `eval_discarded` instead — a terminal event that `pop_eval_pending`
does not pick up again.

## Naming note — two different "discard" concepts

These two things share the word "discard" but mean opposite things about whether
eval ran:

- **`eval_discarded`** (queue event) — eval was **not** run. The node had no
  scorable summary (e.g. `not_relevant`). Terminal: the queue skips it on future
  runs.

- **`score = "discard"`** (eval result field) — eval **did** run and the LLM
  concluded the company is not a match. Stored in `eval_results/`, preceded by
  `eval_done` in the queue.

Same word, opposite meanings re: whether the LLM was called. Worth keeping in
mind when reading logs or writing queue-inspection code.
