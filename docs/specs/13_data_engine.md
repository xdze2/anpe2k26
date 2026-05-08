---
status: draft
---

# Data engine — design v2

This document motivates a refactor of the enrichment pipeline toward a general-purpose
data engine, and lays out the design choices and open questions.

---

## Motivation

The current `pipeline.py` is built around a **two-phase step**: fetch → summarize. The
queue (`fetch.jsonl`), the retry logic, and the step dispatch are all written with this
specific shape in mind. As the pipeline grows — eval, profile update, SIREN fetch,
URL fetch — each new step is bolted on with its own ad-hoc queue and state file.

Three concrete problems this creates:

1. **The two-phase step is a special case of a graph.** `fetch → summarize` is just two
   nodes connected by a queue. The eval step is a third node. The current code does not
   express this — it encodes the topology in control flow inside `enrich_step()`.

2. **Async batching is constrained by the per-node JSONL design.** Running 50 nodes in
   parallel with rate limiting requires a scheduler that understands queues as first-class
   objects, not one that pops items inside a loop.

3. **Decisions and execution are conflated.** Whether a step _can_ run, whether it
   _should_ run, and _running_ it are tangled together. For an exploration tool this
   matters: even when a step is doable, the user often does not want to run it on every
   node — only the promising ones, only the ones matching some filter, only after a
   manual review.

The goal of this refactor is not to add features. It is to make the existing pipeline
easier to extend, easier to reason about, and to give the user explicit control over
_what_ runs, separately from _how_ it runs.

---

## Core model: `scan | filter | put | run`

The engine is a four-stage pipe. Each stage has a single responsibility:

```
  scan        →    filter      →    put          →    run
  ─────            ──────            ───                ───
  what's            what's            commit             execute
  doable?           wanted?           it                 it
```

- **`scan`** — pure function over current state. For a given step, enumerate every
  `(node_id, args)` tuple that _could_ run: inputs exist, no equivalent output is
  already on disk. No side effects. Produces _candidates_.

- **`filter`** — policy. Drop candidates by score, by tag, by manual deny-list, by
  "user already reacted." Implemented as hardcoded per-step flags on `scan`, not a
  generic predicate language (see "Filter ergonomics" below).

- **`put`** — the only writer to the queue. Inserts a fully-resolved run description.
  Idempotent: putting the same `(step, version, args)` twice is a no-op.

- **`run`** — drains the queue. Claims a pending item, executes the step's work
  function, writes outputs to the vault and to the event log, marks done. Knows
  nothing about why an item was put there.

These stages are independently invokable. Each one is a useful command on its own:

```bash
anpe scan eval                              # all doable eval candidates
anpe scan eval --min-score=7                # filtered (hardcoded flag)
anpe scan eval --min-score=7 | anpe put     # actually schedule
anpe run                                    # drain the queue with rate limits
```

This is the abstraction. Everything below is the substrate that supports it.

### Why this shape

The natural alternative — Make-style "if doable and stale, run" — is wrong for an
exploration tool. Even when an eval is doable on every node, you do not want to spend
50 LLM calls re-evaluating nodes you have already discarded. The user's interest is a
first-class input to scheduling, not an afterthought.

Conversely, a pure work-queue model ("the producer of the previous step calls
`put()`") makes the staleness question external: when the profile changes, _something_
has to know to re-enqueue eval for every node. By making `scan` a pure function over
the data graph, that question has a uniform answer: re-run `scan eval` and you see
every node whose eval is now stale.

`scan` is the Make-like pull-staleness layer.
`filter` is the layer Make does not have and that an exploration tool needs.
`put` is the commit point.
`run` is pure execution.

### Capability vs. intent vs. execution

Three concerns, three stages:

| Concern    | Question                             | Stage          |
| ---------- | ------------------------------------ | -------------- |
| Capability | Are inputs present? Step applicable? | `scan`         |
| Intent     | Should this actually run?            | `filter`+`put` |
| Execution  | Run it.                              | `run`          |

The spec's earlier draft conflated capability with intent. This decomposition is
the central design move.

---

## Args and outputs — the data shape

Every step is a function `args → outputs`, where both are JSON dicts. This is the
whole interface.

```python
@dataclass
class Candidate:
    step: str
    node_id: str
    args: dict          # everything the work function needs
    context: dict       # signals for filtering, populated by scan
```

`args` carries everything the work function needs to run: scalar parameters
(keywords, tool slugs), and **vault URIs as strings** (e.g. `args["raw_file"] =
"abc123/raw/2026-05-08T1200_homepage.html"`). There is no separate "files" field —
a URI is just a string the work function knows how to load. Convention: keys
suffixed `_uri` are vault references.

`outputs` mirrors `args`: also a JSON dict, may mix inline values and vault URIs.
Eval can write `{"score": 7, "fit": "...", "reasoning_uri": "..."}` — the score is
inline (cheap to read at scan time when filtering), the long reasoning lives in
the vault. The work function decides what goes inline vs. into the vault.

`context` is what makes filtering expressive: `scan` joins relevant signals
(latest eval score, last reaction, NAF code, ...) onto each candidate so the
filter flags have something to bite on. `context` lives only in the candidate
stream; it is not stored in the queue.

### node_id for process-level steps

Most steps are per-company: `node_id` is the company node directory name. Some
steps are not — `bootstrap` produces a company listing from the user profile,
with no company node to attach to. These use a sentinel string prefixed with
`_` (e.g. `_bootstrap`). The underscore is a convention: real node ids never
start with `_`, so there is no collision risk.

This feels slightly off because `node_id` implies "a company node," but it is
pragmatic: the queue, vault URI scheme, and history queries all work unchanged.
The alternative — a separate nullable column or a union type — adds complexity
for a rare case. If the number of process-level steps grows, revisit.

---

## What each step declares

A step is defined by:

- **`name`** — `fetch`, `summarize`, `eval`, ...
- **`version`** — bumped when logic changes; participates in content addressing.
- **`scan(queue, vault, **filter_flags) -> list[Candidate]`** — enumerates doable
  candidates. `queue` and `vault` are the two environment services: `queue` for
  reading event history (e.g. skip items already done), `vault` for reading
  existing artifacts (e.g. the bootstrap listing). Both are passed explicitly so
  the caller controls which database connections are open — same rationale as not
  using module-level singletons for DB clients.
- **`work(args, vault, log) -> dict`** — the work function. Loads inputs from `args`,
  computes, returns an outputs dict. `log` is a per-item sink for progress messages.
- **`rate_gate`** — declares which external resource this step is bound by
  (e.g. `"mistral"`, `"ddg"`, `"siren"`, or `None`). The runner holds one
  `RateGate` per resource name and calls `gate.acquire()` before each
  `work()` call. A gate enforces a **minimum interval between consecutive
  requests** to that resource — not just concurrency — because the binding
  constraint is calls per minute, not simultaneous connections. Steps that
  share the same external quota (e.g. `summarize_ddg` and `eval` both hit
  Mistral) declare the same gate name and therefore share the same throttle.

Steps never call each other. A step writes its outputs to the vault and to the
event log, then stops. Whether downstream work becomes doable is something the
_next_ `scan` discovers.

### `scan` is per-step

Each step knows what its inputs look like and what counts as "already done":

- **`scan summarize`** — for each `(node_id, raw_uri)` where no `sum_*.json`
  exists for that raw file at the current summarizer version → emit a candidate.

- **`scan eval`** — for each `(node_id, summary_uri, profile_uri)` where no
  `eval_*.json` exists for that `(summary, profile)` pair → emit a candidate.

- **`scan fetch`** — different shape: inputs are URLs that do not preexist as
  artifacts. Source is pending targets emitted by summarize (`new_targets`) or
  by seed. Reads from a `targets/` log; emits one candidate per pending target
  not yet fetched.

Fetch is naturally **push-sourced** (new URLs appear from outside the data
graph). Summarize and eval are naturally **pull-sourced** (derived from existing
artifacts). The `scan | filter | put | run` interface accommodates both.

`scan` also surfaces **stale claims**: any item claimed more than 5 minutes ago
without a `done` or `error_*` event is reported as a candidate for retry. See
"Worker crash recovery" below.

### Filter ergonomics

Filtering is **hardcoded per step**, exposed as named flags on `scan`. No generic
predicate language, no DSL, no `eval()`-on-user-string footguns.

```bash
anpe scan eval --min-score=N --exclude-reaction=discard
anpe scan summarize --naf-prefix=62
anpe scan fetch --tool=duckduckgo
```

Each step declares the flags that make sense for its candidate context. If the
same flag combination is used repeatedly, it becomes a shell alias. If a flag
shape recurs across multiple steps, it becomes shared infrastructure. We add a
generic predicate layer only if the hardcoded flags actually start to chafe — not
preemptively.

The line we will not cross: filter does not maintain its own state. Stateful
"skip this node forever" lives in `NodeDir`, exposed through a context field
that flags can read.

---

## Vault — artifact storage

```python
class Vault:
    def save(self, uri: str, data: bytes) -> str: ...  # returns canonical uri
    def load(self, uri: str) -> bytes: ...
```

The URI scheme decouples the engine from the storage backend. The current
implementation uses the filesystem. A future implementation could use S3,
MongoDB, or a local SQLite blob store — the steps don't change.

URI convention: `{node_id}/{stage}/{timestamp}_{slug}.{ext}` — stable,
human-readable, trivially mapped to a filesystem path or a database key.

**Vault is write-once.** Every artifact path includes a creation timestamp;
files are never overwritten or modified after creation. This invariant is what
makes the rest of the design simple: the URI string _is_ the content identifier.
No need to re-hash file contents to detect changes — if the URI is the same,
the bytes are the same.

---

## Queue — concurrency-safe work log

The queue is the substrate `put` writes to and `run` claims from. It is **not the
abstraction** — `scan | filter | put | run` is. The queue is an implementation
concern that supports them.

### Item identity is content-addressed

```python
uid = hash(step, version, args)
```

Because the vault is write-once, hashing the args (which contain URI strings,
not file contents) is enough — the URI uniquely identifies the bytes.

This makes `put` idempotent: putting the same logical run twice produces the
same uid, and the second insert is a no-op. It also kills a class of bugs:
re-running `scan | put` after a crash does not duplicate work; loop-backs
(summarize emitting new fetch targets that resolve to URLs already fetched)
collapse cleanly.

Crucially, this gives free staleness detection. When the profile file changes,
its URI changes (new timestamp), so every eval candidate gets a new uid —
`scan eval` naturally surfaces every node whose eval is now stale, with no
external "invalidate" trigger.

### Queue interface

```python
class Queue:
    def put(self, candidate: Candidate, force: bool = False) -> str: ...
    def claim(self, step: str, worker_id: str) -> Item | None: ...
    def mark_done(self, uid: str, outputs: dict): ...
    def mark_error(self, uid: str, reason: str, retryable: bool): ...
    def pending(self, step: str) -> list[Item]: ...
    def stale_claims(self, step: str, older_than_s: int = 300) -> list[Item]: ...
```

`put` is idempotent by default. `force=True` perturbs the uid (with a nonce) so
the run is enqueued as a distinct item — for the "the LLM gave a bad answer,
re-run this exact eval" case where bumping the step version would be too broad.

`claim` takes a step name, not a uid: the runner is generic ("give me any
pending item for step X"). For debug ergonomics, `anpe run --uid=...` exists as
a separate code path.

`stale_claims` returns items claimed but not finished within the timeout
window. Used both by `scan` (to surface them as retry candidates) and by the
runner's claim sweep (to auto-recover from worker crashes).

### Queue persistence — SQLite as an append-only event log

State is derived from an append-only event log. No rows are ever updated or
deleted. This preserves the audit trail and matches the spirit of the current
JSONL format — just unified across nodes and steps.

```sql
CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,  -- global ordering
    uid         TEXT NOT NULL,    -- content-addressed item id
    node_id     TEXT NOT NULL,
    step        TEXT NOT NULL,    -- 'fetch' | 'summarize' | 'eval' | ...
    event       TEXT NOT NULL,    -- 'put' | 'claimed' | 'done' | 'error_retry' | 'error_abort'
    ts          TEXT NOT NULL,
    args        TEXT,             -- JSON dict (put event)
    outputs     TEXT,             -- JSON dict, inline values + URIs (done event)
    worker_id   TEXT,             -- (claimed event)
    error       TEXT              -- error reason (error_* events)
);

CREATE INDEX idx_events_step_uid ON events (step, uid, id);
```

Six payload columns. The mental model: a step is `args → outputs`, both JSON
dicts, both potentially containing vault URIs as strings. Plus a worker id when
claimed and an error reason when failed. That's it.

Current state of an item = its latest event. Pending items for a step:

```sql
SELECT uid, args
FROM events
WHERE step = ?
  AND id IN (SELECT MAX(id) FROM events WHERE step = ? GROUP BY uid)
  AND event IN ('put', 'error_retry');
```

Per-node history (equivalent to today's `cat fetch.jsonl`):

```sql
SELECT * FROM events WHERE node_id = ? ORDER BY id;
```

Atomic claim is a single transaction: SELECT a pending uid, INSERT a `claimed`
event. SQLite serializes writes, so two workers racing each execute
sequentially — the second finds the item already claimed and backs off.

The per-node JSONL files become _views_ over the global log, regenerated on
demand. The global log is the source of truth.

---

## Runner

The runner's job: **drain the queue, respect rate limits, sweep stale claims,
stop cleanly.**

```python
CLAIM_TIMEOUT_S = 300   # 5 minutes — runs are expected to be small

class Runner:
    async def run_until_empty(self):
        tasks = [
            asyncio.create_task(self._worker(step))
            for step in self.steps
            for _ in range(step.concurrency)
        ]
        await asyncio.gather(*tasks)

    async def _worker(self, step: Step):
        while True:
            self._sweep_stale_claims(step)   # re-mark as error_retry
            item = await self.queue.claim(step.name, worker_id=...)
            if item is None:
                if self._all_quiescent():
                    return
                await asyncio.sleep(POLL_INTERVAL)
                continue
            await self.gates[step.rate_gate].acquire()  # min-interval throttle
            try:
                outputs = await step.work(item.args, self.vault)
                self.queue.mark_done(item.uid, outputs)
            except RetryableError as e:
                self.queue.mark_error(item.uid, str(e), retryable=True)
            except FatalError as e:
                self.queue.mark_error(item.uid, str(e), retryable=False)

    def _sweep_stale_claims(self, step: Step):
        for stale in self.queue.stale_claims(step.name, CLAIM_TIMEOUT_S):
            self.queue.mark_error(stale.uid, "claim timeout", retryable=True)
```

Runs are expected to complete in well under 5 minutes (single LLM call, single
fetch). A claim that exceeds the timeout is treated as a crashed worker and
re-marked as `error_retry` — the next claim will pick it up. This handles
crashes uniformly with other retryable errors.

The runner does **not** trigger downstream work. It does not call `scan` or
`put`. A run finishing simply marks the queue done; whether new work becomes
doable is something the next `scan` invocation discovers. This is the rule that
keeps intent and execution separated.

### error_retry is between sessions, not within a session

`error_retry` means "try again next time `anpe run` is invoked" — not "retry
immediately in this worker loop." Within a single runner session, each uid is
attempted at most once. The runner tracks attempted uids and passes them as
`skip_uids` to `claim()`, which excludes them from the SQL query.

This avoids an infinite retry loop: without the skip, a work function that
always raises `RuntimeError` would be claimed, fail, be re-marked `error_retry`,
claimed again, and cycle forever. The queue stays non-empty, the worker never
exits.

The stale-claim sweep (`CLAIM_TIMEOUT_S`) is a separate concern: it handles
items claimed by a worker that crashed before finishing — those get a fresh
`error_retry` event and are available to the *next* session. It does not
interact with the within-session skip set.

### Rate limiting

One `RateLimiter` per external resource (OpenRouter, DDG, SIREN), shared across
all steps that hit it. Token bucket with configurable rate and burst. This is
the right granularity: OpenRouter's quota applies to all LLM steps combined,
not per step.

---

## How the current pipeline maps to this model

The existing `fetch → summarize → eval` chain becomes three steps, each with
its own `scan`:

- **fetch** — `scan` reads pending targets (today's open entries in
  `fetch.jsonl`, tomorrow's `targets/` log). Work fetches the URL, writes raw
  data to the vault.
- **summarize** — `scan` finds `(node, raw_uri)` pairs with no summary at the
  current summarizer version. Work calls the LLM, writes `sum_*.json`. New
  targets emitted by the summary land in the `targets/` log, which fetch will
  pick up on its next `scan`.
- **eval** — `scan` finds `(node, summary_uri, profile_uri)` triples with no
  matching eval. Work calls the LLM, writes `eval_*.json` and emits inline
  `{score, fit}` into the event-log outputs.

The current "fetch already done, retry summarize" branch (the `if` inside
`enrich_step()`) disappears: `scan summarize` includes any raw_file lacking a
summary, regardless of whether fetch ran in this session or last week. The
state-machine drawing in `pipeline.py:1-13` is replaced by "look at the event
log."

The "loop-back" cycle (summarize → new_targets → fetch) stops being a special
case. Summarize writes `new_targets` to the targets log; the next `scan fetch`
sees them. No queue-to-queue plumbing.

---

## CLI surface

The four core commands map to the four stages. Each is independently useful.

```bash
anpe scan <step> [--step-specific-flags]   # list candidates as JSON, one per line
anpe put                                   # stdin → queue
anpe run [--step=...] [--budget=...]       # drain queue, optionally limited

# Convenience composition:
anpe step <step> [flags]                   # = scan ... | put ; then run
```

Filtering happens inside `scan` via hardcoded flags; there is no separate
`filter` command. This keeps the model simple while leaving room to introduce
one later if the flags ever stop being enough.

---

## Design choices and alternatives

### Why not Make / DVC?

Make and DVC handle staleness propagation beautifully but cannot express:

- "rate-limit OpenRouter across all LLM calls"
- "10 parallel async workers per step"
- "filter candidates by current eval score before scheduling"

The first two are why we need a queue and a runner at all. The third is why we
need filtering as a first-class concern. `scan` borrows the Make idea (derive
candidates from current state); the rest of the pipe handles what Make does
not.

### Why not push from each step's output?

The earlier draft of this spec had each step's `work()` write directly to a
downstream queue. Three problems:

- Couples each step to the topology of what comes after it.
- Re-runs and loop-backs need ad-hoc cycle handling.
- "Should this run?" has nowhere to live — the producer always commits.

`scan` decouples discovery from production. The producer just writes its
output and stops; discovery is a separate, idempotent, inspectable function.

### Why content-addressed uids

- Idempotent `put`: re-running `scan | put` after a crash is safe.
- Free staleness detection: changing the profile file changes every eval uid.
- Cycle safety: summarize emitting a target URL that was already fetched
  produces the same fetch uid; the duplicate `put` is a no-op.
- Cache reuse: the event log doubles as a result cache (`outputs` is right
  there; the vault holds large artifacts).

The cost is computing input hashes on every `scan`. Negligible — args are tiny
JSON dicts and the vault's write-once invariant means we never re-hash file
contents.

### Why hardcoded filters

A `--filter "expr"` flag invites scope creep ("can we add `or`?", "can we
negate?", "can we reference fields the candidate doesn't expose?"). It also
needs a safe evaluator. Hardcoded per-step flags are the simplest thing that
works for the cases we actually have today — and if a generic predicate layer
is ever justified, the flag definitions are the inventory of what it would
need to support.

### Rate limiting granularity

Per external resource, not per step. `OpenRouterLimiter` is shared by
`summarize` and `eval`; `DDGLimiter` is owned by `fetch`. The runner injects
the limiter into the step at construction time.

---

## Open questions

**Where does `scan eval` get the active profile?** Reading from
`anpe.profile.active_profile_file()` at scan time is correct but means scan
has a runtime dependency on the profile module. Alternative: pass
`--profile=<path>` explicitly. Probably both — default to active, allow
override.

**Quiescence with loop-backs.** `run` stops when the queue is empty _and_ no
workers are in-flight. Loop-back works because `scan` is not run automatically
— a new fetch becoming doable does not auto-enqueue. The user (or a wrapping
script) re-runs `scan | put` if they want another pass. This is intentional:
it preserves the rule that intent is explicit.

**Per-node JSONL views.** Today's `fetch.jsonl` is human-readable and
grep-able. If the global log becomes the source of truth, we lose `cat
node_xyz/fetch.jsonl`. Solution: `anpe node history <node_id>` regenerates
the per-node view from the event log. Cheap, always current, no drift.

**POC, no migration.** We are still in POC mode — no need for a JSONL
migration script. Throw away the current `fetch.jsonl` and rebuild from
scratch when the new engine lands.

---

## Implementation path

Four independent chunks, bottom-up. Chunks 1–3 add new code without touching
`pipeline.py` — the existing pipeline keeps working throughout. Chunk 4 is
where it gets replaced.

**Storage root:** `user_vault/` — a new top-level directory alongside
`user_data/`. The two systems are fully separated until the migration is done.

### Chunk 1 — `Vault`

`anpe/engine/vault.py`. Write-once artifact store: `save(uri, data) -> str`,
`load(uri) -> bytes`. URI convention `{node_id}/{stage}/{ts}_{slug}.{ext}`
maps directly to a path under `user_vault/`. No dependencies.

Tests: save/load round-trip, write-once enforcement (overwrite raises), URI
format is stable.

### Chunk 2 — `Queue`

`anpe/engine/queue.py`. The six-method interface over a single SQLite file
(`user_vault/queue.db`). Append-only `events` table. `put` is idempotent via
`uid = hash(step, version, args)`. `claim` is a single write transaction.

Tests: put idempotency, claim atomicity (two concurrent claims, only one
wins), mark_done/mark_error round-trip, pending query, stale_claims.

### Chunk 3 — `Step` definitions (scan + work)

`anpe/engine/steps/`. A `Step` dataclass (`name`, `version`,
`scan(**flags) -> list[Candidate]`, `work(args, vault) -> outputs`). Port the
three existing steps as concrete implementations:

- `SummarizeStep.scan()` — walks node dirs, finds `(node, raw_uri)` pairs
  with no matching summary at the current version. Replaces the equivalent
  logic inside `enrich_step()`.
- `EvalStep.scan()` — finds `(node, sum_uri, profile_uri)` triples with no
  matching eval.
- `FetchStep.scan()` — reads pending targets from the targets log.

`work()` bodies delegate to the existing `tool.fetch()`, `tool.summarize()`,
and `eval.run()` — no rewrite of the LLM logic.

Tests: `scan()` returns the right candidates given a fixture node directory.
`work()` tested with a fake Vault.

### Chunk 4 — `Runner` + CLI wiring

`anpe/engine/runner.py`. Async worker loop: `run_until_empty`, per-step
workers, stale-claim sweep, rate limiters injected at construction. Then wire
`anpe scan`, `anpe put`, `anpe run` as Click subcommands replacing the old
`anpe enrich` path.

Tests: runner drains a pre-populated queue, stale claim is recovered,
`anpe scan eval --min-score=7` filters correctly. Integration test: `scan |
put | run` against a fixture, verify the event log.
