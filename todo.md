# Engine review — follow-up todo

Tracks fixes from the review of `anpe/engine/` against `docs/specs/13_data_engine.md`.
Tackle top-down; each item is independently shippable.

---

## P1 — broken / blocks end-to-end

- [ ] **`EvalStep.scan` rewrite** — currently reads old-pipeline `user_data/nodes/<id>/summarize/` and `eval_results/`. Rewire to source from `summarize_ddg` done events (vault `summary_uri`), suppress with `queue.is_done()`, drop the `NodeDir` filesystem walk. Also fix `profile_uri`: it is currently an absolute filesystem path stuffed into a key called `_uri` — either store profile in vault, or rename the key.
  - File: [anpe/engine/steps/eval.py](anpe/engine/steps/eval.py)
  - Tests: rewrite `TestEvalStepScan` to seed `summarize_ddg` done events, no `NODES_DIR` monkeypatch.

- [ ] **`BootstrapStep.refresh` is silently broken** — `args["refresh"]` is hardcoded to `False` at scan time, so `work()` never refreshes even if `scan(refresh=True)` is called. Drop `refresh` from `args` entirely (it is a scan-time decision); pass it via a different path or reconsider whether `force=True` on `put` is the right primitive for "re-run anyway".
  - File: [anpe/engine/steps/bootstrap.py:34-48](anpe/engine/steps/bootstrap.py#L34-L48)

## P2 — API hygiene (removes private-API reaches)

- [x] **Add `Queue.done_events(step)` public method.** Two steps currently reach into `queue._conn` to run the same SQL.
  - File: [anpe/engine/queue.py](anpe/engine/queue.py)
  - Callers to migrate: [fetch_ddg.py:80-86](anpe/engine/steps/fetch_ddg.py#L80-L86), [summarize_ddg.py:83-90](anpe/engine/steps/summarize_ddg.py#L83-L90)

- [x] **Echo `siren_uri` through `fetch_ddg` outputs.** Lets `summarize_ddg.scan` read it from the done event like everything else; deletes `_siren_uri_for_ddg_event` and its private SQL query.
  - Files: [fetch_ddg.py:77](anpe/engine/steps/fetch_ddg.py#L77), [summarize_ddg.py:34, 93-102](anpe/engine/steps/summarize_ddg.py#L34)

## P3 — spec/code drift

- [x] **Update spec to match Vault interface.** Spec says `save(uri, data)`; code is `store(node_id, step, slug, ext, data)`. Code is better, fix the spec.
  - Files: [13_data_engine.md:233](docs/specs/13_data_engine.md#L233)

- [ ] **Reconcile Queue interface (spec vs. code).** Spec lists `mark_done(uid, outputs)` etc.; code requires extra `step, node_id` args. Decide: either denormalise (queue looks up step/node_id from the put event) or update the spec.
  - Files: [13_data_engine.md:280-288](docs/specs/13_data_engine.md#L280-L288), [queue.py:127-140](anpe/engine/queue.py#L127-L140)

- [ ] **`count` flag on scan is a limit, not a filter.** `count=10` default silently caps emission. Rename to `--limit`, drop the default (require explicit value), and document; or remove the cap and rely on `put` being idempotent.
  - Files: [fetch_siren.py:25](anpe/engine/steps/fetch_siren.py#L25), [fetch_ddg.py:25](anpe/engine/steps/fetch_ddg.py#L25)

- [ ] **`targets/` log loop-back: implement or delete from spec.** Spec describes summarize → new_targets → fetch loop-back; pipeline doesn't do it. Decide which.
  - Files: [13_data_engine.md:198-204, 441-455](docs/specs/13_data_engine.md#L198-L204)

## P4 — robustness

- [ ] **Define explicit `RetryableError` / `FatalError` exceptions.** Replace the `RuntimeError` vs `Exception` heuristic in the runner with a typed contract; document on `Step.work`.
  - Files: [runner.py:108-119](anpe/engine/runner.py#L108-L119), [base.py](anpe/engine/steps/base.py), all step `work()` bodies

- [ ] **Stale-claim sweep cooldown.** Sweep runs every loop iteration and can write duplicate `error_retry` events under contention. Limit to once per worker startup, or rate-limit (e.g. 60s).
  - File: [runner.py:128-130](anpe/engine/runner.py#L128-L130)

- [ ] **`force=True` should not change uid length.** Move the nonce into `args["_nonce"]` so the uid stays content-addressed and a fixed length.
  - File: [queue.py:64-67](anpe/engine/queue.py#L64-L67)

- [ ] **Handle `asyncio.CancelledError` explicitly in runner.** Currently caught by `except Exception` → marked as fatal. Should propagate cancellation instead.
  - File: [runner.py:114](anpe/engine/runner.py#L114)

## P5 — small cleanups

- [x] **Single `USER_VAULT_DIR` constant.** Defined twice, in vault.py and queue.py.

- [x] **`StepLogger` timestamp typo.** `"%Y-%m-%d %H:%M.%S"` → `"%Y-%m-%d %H:%M:%S"`.
  - File: [logger.py:11](anpe/engine/logger.py#L11)

- [ ] **Document the `_attempted` / `skip_uids` contract on `Queue.claim`.** Right now the "no within-session retries" rule is invisible from the queue API.
  - Files: [queue.py:81](anpe/engine/queue.py#L81), [runner.py:48](anpe/engine/runner.py#L48)
    > ... ?

- [-] **Consistent step `version` scheme.** Mix of `"v1"`, `"v2"`, `SUMMARIZE_VERSION + ".2"`, `EVAL_VERSION`. Pick one.

  > skip

- [x] **Bump `_content_uid` to 32 hex chars** (or document the 64-bit choice).
  - File: [queue.py:42](anpe/engine/queue.py#L42)

- [ ] **Assert sentinel node_id convention.** Real node*ids must not start with `*`.
  - File: [anpe/prospect/seed.py](anpe/prospect/seed.py) (`node_id_for`)
    > what?
