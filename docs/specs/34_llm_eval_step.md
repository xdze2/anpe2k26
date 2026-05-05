---
status: draft
---

# LLM eval step

The eval step scores a node against the current user profile. It is a separate
pipeline from the fetch/summarize cycle — decoupled state machine, decoupled
storage, triggered independently.

## Purpose

After enrichment, each node has a _summary_ but no signal on whether it
matches the user. Eval produces that signal: a score and a one-line reason that
lets the user quickly validate or override. It also drives what gets surfaced in
the review session.

---

## Storage

Per the data flow conventions (`12_data_flow.md`), eval follows the same
append-only queue + immutable results pattern as the fetch pipeline.

```
nodes/<node_id>/
  eval_queue.jsonl        ← append-only event log (queue + history)
  eval_results/
    eval_<timestamp>_<slug>.json   ← one result per run, never overwritten
```

### eval_queue.jsonl — event types

| event        | meaning                                                           |
| ------------ | ----------------------------------------------------------------- |
| `put`        | node enqueued for eval; carries `uid`, `sum_file`, `profile_file` |
| `eval_done`  | result saved; carries `result_file` path                          |
| `eval_error` | LLM call failed; retryable                                        |
| `reeval`     | re-queue after profile update; carries `reason`                   |

State per uid is the last event. Pending = last event is `put`, `eval_error`,
or `reeval`.

### eval*results/eval*<timestamp>\_<slug>.json — fields

```json
{
  "ts": "...",
  "eval_uid": "...",
  "sum_file": "summarize/sum_ddg_..._ok_....json",
  "profile_file": "../../profile_20260505T1200.md",
  "eval_version": "a3f9c1",
  "model": "...",
  "score": "good",
  "fit": "produit propre, IA embarquée, équipe <30",
  "dealbreakers": [],
  "uncertainty": "low",
  "duration_s": 1.4
}
```

`sum_file` and `profile_file` are the exact inputs used — both are immutable
records, so this is a reproducible snapshot of what the eval saw.

`eval_version` is a short hash of the system prompt + model name, same mechanism
as `SUMMARIZE_VERSION`. Bumping it marks all existing evals as stale.

---

## Score values

| score     | meaning                            | action               |
| --------- | ---------------------------------- | -------------------- |
| `good`    | clear match                        | surface to user      |
| `maybe`   | matches but something is uncertain | surface with reason  |
| `discard` | clear non-match                    | skip in review       |
| `enrich`  | not enough data to decide          | re-queue fetch steps |

`enrich` must name a specific gap in `fit` ("taille inconnue", "domaine ambigu").
It must not fire as a default fallback when data is thin — use `maybe` with
`uncertainty: high` instead.

`fit` is always one sentence naming the deciding factor. It is the primary
correction surface: if the user disagrees with the score, the `fit` sentence is
what they respond to, and that response feeds the profile update.

---

## Triggers

**After summarize_done** — the fetch pipeline enqueues an eval `put` automatically
when a node reaches `summarize_done`. The `sum_file` is the result file just
written; `profile_file` is the currently active profile.

**After profile update** — a `reeval` command (analogous to `resummarize`) scans
all nodes whose last eval `profile_file` differs from the current active profile
and appends a `reeval` event. The next eval run picks them up.

---

## Staleness

An eval is stale when either input has changed:

- `profile_file` in the result differs from the current active profile → profile
  updated since eval ran.
- `eval_version` in the result differs from the current constant → prompt or model
  changed.

Both are detectable by scanning `eval_queue.jsonl` and reading the linked result
file — no external metadata needed.

---

## Decoupling from the fetch pipeline

Eval runs in its own loop, separate from `enrich_step`. The fetch pipeline appends
a `put` to `eval_queue.jsonl` as a side effect of `summarize_done`, but does not
wait for eval to complete. This keeps the two pipelines independently runnable:

```
anpe prospect run   # fetch + summarize only
anpe prospect eval  # eval only, processes pending queue
```

Eval reads `sum_file` directly — it does not read `summary.md`. This is the
traceable input link required by the data flow design.
