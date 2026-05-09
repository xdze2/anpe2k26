# Engine — follow-up todo

After the data-engine refactor and partial cleanup. New items come from the
broad-view design review on 2026-05-09 (see dev log of that day for context).
Tackle top-down; each item is independently shippable.

---

## P1 — design moves with the highest leverage

- [ ] **Make the step graph explicit via `inputs_from`.**
  Today every `scan()` opens with `for ev in queue.done_events(_UPSTREAM):` where
  `_UPSTREAM` is a private string constant. The pipeline shape
  `bootstrap → fetch_siren → fetch_ddg → summarize_ddg → eval → review` lives
  nowhere as data — only by grep. Lift it to `Step.inputs_from: list[str]`
  alongside `name`/`version`. Unblocks the auto-loop driver, `anpe steps --graph`
  visualization, and registry-time validation that referenced upstreams exist.
  - Files: [fetch_ddg_step.py:16](anpe/steps/fetch_ddg_step.py#L16),
    [summarize_ddg_step.py:15](anpe/steps/summarize_ddg_step.py#L15),
    [eval_step.py:14](anpe/steps/eval_step.py#L14),
    [review_step.py:17](anpe/steps/review_step.py#L17),
    [fetch_siren_step.py:15-16](anpe/steps/fetch_siren_step.py#L15-L16),
    [engine/base.py](anpe/engine/base.py), [engine/registry.py](anpe/engine/registry.py)

- [ ] **Introduce `scope` as a first-class step attribute, replacing the `_bootstrap` sentinel pattern.**
  `node_id` is doing two jobs: partition key for vault paths/queue rows, *and*
  "what entity this work concerns." Bootstrap and (future) profile-update are
  process-level — there is no entity. The `_bootstrap` sentinel papers over this
  and the spec already calls it out as "slightly off."
  Make `Step.scope: Literal["node", "global"]` (or similar) explicit. Steps
  with `scope="global"` use a fixed key (e.g. `_global` or the step name) for
  the partition column, and the vault routes them under a global directory.
  Per-node steps continue to carry a real `node_id`. Removes the smell, makes
  room for future global steps without inventing more sentinels.
  - Files: [bootstrap_step.py:16](anpe/steps/bootstrap_step.py#L16),
    [engine/base.py](anpe/engine/base.py), [engine/queue.py](anpe/engine/queue.py),
    [engine/vault.py](anpe/engine/vault.py)

- [ ] **`scan()` returns `Iterator[Candidate]` instead of `list[Candidate]`.**
  Three steps already paper over the eager-list problem with a `count: int = 10`
  parameter — invisible at the CLI, hardcoded, only on some steps. After
  bootstrap with thousands of companies, scan walks all of them eagerly.
  A generator makes scan lazy: caller pulls until budget is exhausted, the
  `count` flag goes away, and `fetch_ddg.scan` stops loading every siren JSON
  upfront. CLI `scan | put | run` works unchanged (one candidate per line).
  - Files: all `*_step.py` `scan()` methods, [engine/base.py](anpe/engine/base.py),
    [cli.py:432, 567](anpe/cli.py#L432)

- [ ] **Per-rate-gate budgets in the runner.**
  The current `--budget=N` on `run` counts items processed
  ([runner.py:54](anpe/engine/runner.py#L54), [cli.py:492](anpe/cli.py#L492)) —
  but "spend at most 50 LLM calls" maps to gate acquisitions, not items.
  fetch_siren and fetch_ddg shouldn't count against an LLM budget; bootstrap
  shouldn't count at all.
  Shape: `Runner.run(budgets={"mistral": 50, "ddg": 200})`, decremented inside
  the gate's `acquire()`. When a gate hits zero, downstream workers stop
  claiming. Item-count budget can stay as a separate cap. This is the one
  budget the user actually has in their head.
  - Files: [engine/rate_gate.py](anpe/engine/rate_gate.py),
    [engine/runner.py](anpe/engine/runner.py),
    [steps/api_throttles.py](anpe/steps/api_throttles.py), [cli.py](anpe/cli.py)

- [ ] **`anpe loop` — drive the whole graph to quiescence.**
  Falls out almost for free once `inputs_from` and gate-budgets exist. Walks
  the graph topologically, scan+put each step, run, re-scan downstream
  (newly-done items unlock new candidates), repeat until quiescent or any
  budget hits zero. Replaces the current 5-command session ritual
  (`step bootstrap`, `step fetch_siren`, ...).
  Intent stays explicit — the user invokes `anpe loop`; the engine still does
  not auto-trigger between sessions.
  - Files: [cli.py](anpe/cli.py), new driver in [engine/](anpe/engine/)

## P2 — leftover from the prior pass

- [ ] **`BootstrapStep.refresh` is silently broken.**
  `args["refresh"]` is hardcoded to `False` at scan time, so `work()` never
  refreshes even if `scan(refresh=True)` is called. Drop `refresh` from `args`
  entirely (it is a scan-time decision); pass it via a different path or
  reconsider whether `force=True` on `put` is the right primitive for "re-run
  anyway."
  - File: [bootstrap_step.py:25-48](anpe/steps/bootstrap_step.py#L25-L48)

- [ ] **Reconcile Queue interface (spec vs. code).**
  Spec lists `mark_done(uid, outputs)` etc.; code requires extra `step, node_id`
  args. Decide: either denormalise (queue looks up step/node_id from the put
  event) or update the spec.
  - Files: [13_data_engine.md:280-288](docs/specs/13_data_engine.md#L280-L288),
    [queue.py:127-140](anpe/engine/queue.py#L127-L140)

- [ ] **`targets/` log loop-back: implement or delete from spec.**
  Spec describes summarize → new_targets → fetch loop-back; pipeline doesn't
  do it. Decide which.
  - Files: [13_data_engine.md:198-204, 441-455](docs/specs/13_data_engine.md#L198-L204)

- [ ] **Wire `prospect review` to `ReviewStep`.**
  CLI command currently prints a placeholder ([cli.py:221-233](anpe/cli.py#L221-L233)).

- [ ] **Retire `node_dir.py`.**
  Legacy filesystem helpers still imported by `prospect list/status/show/map`.
  Once those commands are ported to read from queue + vault, the module goes.
  - File: [anpe/node_dir.py](anpe/node_dir.py)

## P3 — small cleanups

- [ ] **De-duplicate `node_id`.**
  Stored on `Candidate.node_id` *and* injected into `args["node_id"]` by every
  step except bootstrap. Work functions read `args["node_id"]`. Pick one — keep
  it on the queue row (the partition key), pass to `work(node_id, args, ...)`
  as a separate argument. Removes the inconsistency and ~5 redundant lines.
  - Files: all `*_step.py`

- [ ] **`Args = dict[str, Any]` / `Outputs = dict[str, Any]` aliases.**
  Removes ~15 `# type: ignore[type-arg]` comments across the engine and steps.
  - File: [engine/base.py](anpe/engine/base.py)

- [ ] **Document the `_attempted` / `skip_uids` contract on `Queue.claim`.**
  The "no within-session retries" rule is invisible from the queue API.
  - Files: [queue.py:81](anpe/engine/queue.py#L81), [runner.py:48](anpe/engine/runner.py#L48)

## P4 — flagged, not yet worth fixing

- [ ] **Cursor for `done_events`.**
  `queue.done_events("fetch_siren")` returns *all* historical done events
  forever; scan I/O grows linearly with corpus size. Eventually want
  "scan since event id N." Premature today.
  - File: [queue.py:215-221](anpe/engine/queue.py#L215-L221)
