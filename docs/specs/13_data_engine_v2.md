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

3. **The mental model is harder to hold than it needs to be.** "Is fetch already done?
   Then skip to summarize" is a workaround for the lack of an intermediate queue. A
   graph of steps connected by queues makes this explicit and debuggable.

The goal of this refactor is not to add features. It is to make the existing pipeline
easier to extend and easier to reason about.

---

## Core abstraction

The engine is a **directed graph of steps connected by queues**.

```
Queue_A  ──[ Step_1 ]──►  Queue_B  ──[ Step_2 ]──►  Queue_C
```

Each step:
- declares one **input queue** it pulls from
- declares one or more **output queues** it pushes to
- has a **work function** that transforms items
- has a **rate limiter** for its external resource (API, DDG, disk)

The **runner** spins async workers per step. Workers pull from the step's input queue,
call the work function, push results to output queues. The runner is the only place
that knows about scheduling, concurrency, and stopping conditions.

Steps are stateless. The queues and the vault are the only shared state.

---

## The three layers

### 1. Vault — artifact storage

```python
class Vault:
    def save(self, uri: str, data: bytes) -> str: ...  # returns canonical uri
    def load(self, uri: str) -> bytes: ...
```

The URI scheme decouples the engine from the storage backend. The current implementation
uses the filesystem (`node_id/raw_data/filename`). A future implementation could use
S3, MongoDB, or a local SQLite blob store — the steps don't change.

URI convention (proposed): `{node_id}/{stage}/{filename}` — stable, human-readable,
and trivially mapped to a filesystem path or a database key.

### 2. Queue — concurrency-safe work log

```python
class Queue:
    step: str       # name of the step that produces into this queue
    version: str    # bumped when the step's logic changes

    def put(self, uid: str, input_uri: str): ...
    def claim(self, worker_id: str) -> QueueItem | None: ...   # atomic
    def mark_done(self, uid: str, output_uri: str, run_hash: str): ...
    def mark_error(self, uid: str, reason: str, retryable: bool): ...
    def get_pending(self) -> list[QueueItem]: ...
```

`claim()` is the critical operation: it atomically transitions an item from `pending`
to `claimed`, preventing two workers from processing the same item. On the filesystem
this can be implemented as a directory rename (atomic on POSIX) or a file lock.

**Item identity vs. run identity:**

- `uid` — identifies the *item* (a URL to fetch, a node to evaluate). Assigned at
  `put()` time. Stable.
- `run_hash = hash(uid + step.version)` — identifies the *result* of running this step
  version on this item. Used to name the artifact in the vault. If the step is re-run
  with a new version, the old artifact is preserved under its old hash.

### 3. Step — unit of work

```python
class Step:
    name: str
    version: str
    input_queue: Queue
    output_queues: list[Queue]
    rate_limiter: RateLimiter

    async def work(self, item: QueueItem, vault: Vault) -> StepResult: ...

    async def run_one(self, vault: Vault) -> StepLog:
        item = await self.input_queue.claim(worker_id=...)
        if item is None:
            return StepLog(status="empty")

        run_hash = hash(item.uid + self.version)

        await self.rate_limiter.acquire()
        try:
            result = await self.work(item, vault)
        except RetryableError as e:
            self.input_queue.mark_error(item.uid, str(e), retryable=True)
            return StepLog(status="error_retry")
        except FatalError as e:
            self.input_queue.mark_error(item.uid, str(e), retryable=False)
            return StepLog(status="error_abort")

        output_uri = vault.save(f"{run_hash}/output", result.data)
        self.input_queue.mark_done(item.uid, output_uri, run_hash)

        for q in self.output_queues:
            q.put(uid=run_hash, input_uri=output_uri)

        return StepLog(status="ok", output_uri=output_uri)
```

Steps never call each other directly. A step writes to its output queues; whatever
step declares those queues as its input will pick up the work. The graph topology
lives in the wiring (which queue is whose input), not inside the step logic.

### 4. Runner — scheduler

```python
class Runner:
    steps: list[Step]
    vault: Vault
    workers_per_step: int

    async def run_until_empty(self):
        tasks = [
            asyncio.create_task(self._worker(step))
            for step in self.steps
            for _ in range(self.workers_per_step)
        ]
        await asyncio.gather(*tasks)

    async def _worker(self, step: Step):
        while True:
            log = await step.run_one(self.vault)
            if log.status == "blocked":
                return
            if log.status == "empty":
                await asyncio.sleep(POLL_INTERVAL)
```

The runner is also where you add cross-step concerns: budget limits, stop-on-blocked,
progress logging, graceful shutdown on SIGINT.

---

## How the current pipeline maps to this model

The existing `fetch → summarize` two-phase step becomes two steps with an intermediate queue:

```
[fetch_queue]  ──[ FetchStep ]──►  [fetch_done_queue]  ──[ SummarizeStep ]──►  [summarize_done_queue]
                                                                                         │
                                                                              ──► [fetch_queue]  (new_targets loop-back)
```

The "fetch already done, retry summarize" case — currently handled by an `if` inside
`enrich_step()` — disappears: `fetch_done_queue` already holds the item, `FetchStep`
never sees it again.

The eval pipeline is a third step:

```
[summarize_done_queue]  ──[ EvalStep ]──►  [eval_done_queue]
```

No new queue files needed — `eval_queue.jsonl` becomes the `summarize_done_queue`.

---

## Design choices and alternatives

### Push vs. pull

**Pull (recommended):** each step polls its input queue. The runner decides when to
schedule. Steps are unaware of what comes after them — they write to output queues
and stop. Easy to inspect (look at any queue to see what's waiting), easy to resume
(workers restart and pull from where they left off).

**Push:** a step calls `next_step.put()` directly when done. Simpler to write but
couples the step to the downstream topology. If you add a step between two existing
ones, you edit the upstream step. Harder to inspect and debug.

The current code is effectively pull — the runner calls `enrich_step`, which pops
from the node's queue. This design makes it explicit.

### Queue scope: per-node vs. global

**Per-node (current):** each node has its own `fetch.jsonl`. Good isolation, trivial
to inspect one company's history, no contention between nodes. Scheduling is awkward:
to saturate a rate limit you need to interleave nodes in the runner, not drain one at a time.

**Global per step (recommended for async batching):** one queue per step, all nodes
mixed. Workers pull items regardless of node — better bin-packing, fewer idle workers.
Costs: `claim()` needs a locking mechanism (see open questions); per-node history
requires filtering the global log by `node_id`.

A hybrid is possible: keep per-node storage for artifacts, but maintain a global
pending index per step that the runner uses for scheduling. The queue's `put()` writes
to both; `claim()` reads only the global index.

### Rate limiting

Each step that calls an external resource declares a `RateLimiter`:

```python
class RateLimiter:
    async def acquire(self): ...  # blocks until a slot is available
```

Simple implementation: token bucket with configurable rate (requests/second) and
burst. One limiter per external resource (OpenRouter, DDG, SIREN) — shared across
all steps that use it. This is the right granularity: OpenRouter's rate limit applies
to all LLM steps combined, not per step.

---

## Open questions

**Atomic claim on the filesystem.**
The simplest implementation of `claim()` is to move a file from `pending/` to
`claimed/`. This is atomic on POSIX. But it changes the on-disk layout significantly
from the current append-only JSONL. Alternative: use `fcntl` file locking on the
JSONL file, or add a `claimed_by` / `claimed_at` field and rely on timeout-based
reclaim. Which is simpler to implement correctly and inspect manually?

**Claimed item timeout / worker crash recovery.**
If a worker claims an item and crashes, the item stays claimed forever. Options:
(a) heartbeat file updated by the worker, swept by the runner; (b) claimed items
older than N minutes are reclaimed on startup; (c) don't bother for now — manual
`anpe queue release <uid>` command. Option (c) is probably fine for the current scale.

**New-targets loop-back.**
The summarize step can emit `new_targets` — new URLs or queries to fetch. These go
back into `fetch_queue`, creating a cycle. In the model above this is expressed as
`SummarizeStep.output_queues = [summarize_done_queue, fetch_queue]`. But `fetch_queue`
items have a `node_id` embedded — the summarize step must know the node of the item
it processed to put new targets in the right place. Is this a problem for the global
queue model, or is `node_id` just a field on every queue item?

**When does the runner stop?**
`run_until_empty` stops when all queues are empty. But with loop-backs (new_targets),
a step may produce new work after other steps have gone idle. The runner needs to
wait for all workers to finish one pass before deciding the system is quiescent. A
simple approach: count in-flight items globally; stop when the count hits zero and
all queues are empty.

**Versioning and reprocessing.**
`run_hash = hash(uid + version)` means bumping `version` triggers reprocessing of
all items. But you might want to reprocess only items whose inputs changed (e.g.
the profile was updated — re-run eval but not fetch). Is version enough, or do you
need content-addressed hashing of the actual inputs?

**Queue persistence format.**
The current JSONL-per-node format is human-readable and append-only, which has served
the project well. A global queue could stay JSONL (one file per step, all nodes
interleaved) or move to SQLite for atomic `claim()` without filesystem tricks. SQLite
is more robust but less inspectable with standard tools. Decide before implementing.

---

## Implementation sketch — SQLite as an append-only event log

SQLite can be used with the same append-only mental model as the current JSONL files —
no rows are ever updated or deleted. State is always derived from the latest event per `uid`.
This preserves the audit trail and makes migration from JSONL trivial (line-by-line import).

### Schema

```sql
CREATE TABLE events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,  -- global ordering, never reused
    uid       TEXT NOT NULL,    -- item identity (random hex, assigned at put)
    node_id   TEXT NOT NULL,
    step      TEXT NOT NULL,    -- 'fetch' | 'summarize' | 'eval' | ...
    event     TEXT NOT NULL,    -- 'put' | 'claimed' | 'done' | 'error_retry' | 'error_abort'
    ts        TEXT NOT NULL,
    -- optional payload
    input_uri   TEXT,
    output_uri  TEXT,
    run_hash    TEXT,
    worker_id   TEXT,
    detail      TEXT
);

CREATE INDEX idx_events_uid_step ON events (step, uid, id);
```

### Deriving state

Current state of an item = its latest event. Pending items for a step:

```sql
SELECT uid, input_uri
FROM events
WHERE step = 'fetch'
  AND id IN (SELECT MAX(id) FROM events WHERE step = 'fetch' GROUP BY uid)
  AND event IN ('put', 'error_retry');
```

Per-node history (equivalent to `cat fetch.jsonl`):

```sql
SELECT * FROM events WHERE node_id = 'abc123' ORDER BY id;
```

### Atomic claim

`claim()` inserts a `claimed` event inside a transaction that first verifies the item
is still pending. SQLite serializes writes, so two workers racing will execute their
transactions sequentially — the second will find the item already claimed and back off.

```python
def claim(self, step: str, worker_id: str) -> QueueItem | None:
    with db:  # serialized transaction
        row = db.execute("""
            SELECT uid, input_uri FROM events
            WHERE step = ? AND event IN ('put', 'error_retry')
            AND id = (SELECT MAX(id) FROM events WHERE step = ? GROUP BY uid HAVING event IN ('put', 'error_retry') LIMIT 1)
        """, (step, step)).fetchone()

        if row is None:
            return None

        db.execute("""
            INSERT INTO events (uid, node_id, step, event, ts, worker_id)
            SELECT uid, node_id, ?, 'claimed', ?, ?
            FROM events WHERE uid = ? ORDER BY id DESC LIMIT 1
        """, (step, now(), worker_id, row["uid"]))

    return QueueItem(uid=row["uid"], input_uri=row["input_uri"])
```

### Migration from JSONL

Each line of `fetch.jsonl` maps directly to one row in `events`. The `event` field
names are already aligned (`put`, `fetch_done` → `done` for the fetch step,
`summarize_done` → `done` for the summarize step, etc.). Migration is a one-off
script; the per-node raw files and summarize result files stay on disk unchanged —
only the queue index moves to SQLite.
