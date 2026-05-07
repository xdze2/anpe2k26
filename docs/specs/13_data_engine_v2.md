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

3. **Decisions and execution are conflated.** Whether a step *can* run, whether it
   *should* run, and *running* it are tangled together. For an exploration tool this
   matters: even when a step is doable, the user often does not want to run it on every
   node — only the promising ones, only the ones matching some filter, only after a
   manual review.

The goal of this refactor is not to add features. It is to make the existing pipeline
easier to extend, easier to reason about, and to give the user explicit control over
*what* runs, separately from *how* it runs.

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
  `(node_id, resolved_inputs)` tuple that *could* run: inputs exist, no equivalent
  output is already on disk. No side effects. Produces *candidates*.

- **`filter`** — policy. Drop candidates by score, by tag, by manual deny-list, by
  "user already reacted." Composable. Stateless predicates over candidate records.

- **`put`** — the only writer to the queue. Inserts a fully-resolved run description.
  Idempotent: putting the same `(step, version, inputs)` twice is a no-op.

- **`run`** — drains the queue. Claims a pending item, executes the step's work
  function, writes outputs to the vault, marks done. Knows nothing about why an
  item was put there.

These stages are independently invokable. Each one is a useful command on its own:

```bash
anpe scan eval                     # show what eval runs are doable
anpe scan eval | anpe filter "score>=7"   # what would be scheduled
anpe scan eval | anpe filter "score>=7" | anpe put   # actually schedule
anpe run                           # drain the queue with rate limits
```

This is the abstraction. Everything below is the substrate that supports it.

### Why this shape

The natural alternative — Make-style "if doable and stale, run" — is wrong for an
exploration tool. Even when an eval is doable on every node, you do not want to spend
50 LLM calls re-evaluating nodes you have already discarded. The user's interest is a
first-class input to scheduling, not an afterthought.

Conversely, a pure work-queue model ("the producer of the previous step calls
`put()`") makes the staleness question external: when the profile changes, *something*
has to know to re-enqueue eval for every node. By making `scan` a pure function over
the data graph, that question has a uniform answer: re-run `scan eval` and you see
every node whose eval is now stale.

`scan` is the Make-like pull-staleness layer.
`filter` is the layer Make does not have and that an exploration tool needs.
`put` is the commit point.
`run` is pure execution.

### Capability vs. intent vs. execution

Three concerns, three stages:

| Concern    | Question                              | Stage          |
|------------|---------------------------------------|----------------|
| Capability | Are inputs present? Step applicable?  | `scan`         |
| Intent     | Should this actually run?             | `filter`+`put` |
| Execution  | Run it.                               | `run`          |

The spec's earlier draft conflated capability with intent. This decomposition is
the central design move.

---

## What each step declares

A step is defined by:

- **`name`** — `fetch`, `summarize`, `eval`, ...
- **`version`** — bumped when logic changes; participates in content addressing.
- **`scan()`** — enumerates doable candidates. Step-specific (see below).
- **`work(item, vault)`** — the work function. Loads inputs, computes, returns output.
- **`rate_limiter`** — shared per external resource (OpenRouter, DDG, SIREN).

Steps never call each other. A step writes its output to the vault and marks the run
done. Whether downstream work becomes doable is something the *next* `scan` discovers.

### `scan` is per-step

Each step knows what its inputs look like and what counts as "already done":

- **`scan summarize`** — for each `(node_id, raw_file)` where no `sum_*.json` exists
  for that raw_file at the current summarizer version → emit a candidate.

- **`scan eval`** — for each `(node_id, latest_sum, active_profile)` where no
  `eval_*.json` exists for that `(sum, profile)` pair → emit a candidate.

- **`scan fetch`** — different shape: inputs are URLs that do not preexist as
  artifacts. Source is pending targets emitted by summarize (`new_targets`) or by
  seed. Reads from a `targets/` log; emits one candidate per pending target not yet
  fetched.

Fetch is naturally **push-sourced** (new URLs appear from outside the data graph).
Summarize and eval are naturally **pull-sourced** (derived from existing artifacts).
The `scan | filter | put | run` interface accommodates both: `scan` for fetch
enumerates pending URLs; `scan` for summarize enumerates raw files lacking summaries.
Same downstream interface, different sources.

### Candidate records

`scan` emits rich records, not just identifiers, so `filter` has something to bite on:

```python
@dataclass
class Candidate:
    step: str
    node_id: str
    args: dict          # scalar params (tool slug, target URL, ...)
    files: list[str]    # vault URIs of input artifacts
    # context for filtering — populated by scan, not by the step
    context: dict       # e.g. {"latest_score": 7, "reaction": "maybe", "naf": "62.01Z"}
```

`context` is what makes filters expressive: `filter "score>=7 and reaction!='discard'"`
works because `scan` already joined the relevant signals. The set of context fields is
step-specific and lives next to the step's `scan` implementation.

---

## Vault — artifact storage

```python
class Vault:
    def save(self, uri: str, data: bytes) -> str: ...  # returns canonical uri
    def load(self, uri: str) -> bytes: ...
```

The URI scheme decouples the engine from the storage backend. The current
implementation uses the filesystem (`node_id/raw_data/filename`). A future
implementation could use S3, MongoDB, or a local SQLite blob store — the steps don't
change.

URI convention: `{node_id}/{stage}/{filename}` — stable, human-readable, and trivially
mapped to a filesystem path or a database key.

---

## Queue — concurrency-safe work log

The queue is the substrate `put` writes to and `run` claims from. It is **not the
abstraction** — `scan | filter | put | run` is. The queue is an implementation
concern that supports them.

### Item identity is content-addressed

```python
uid = hash(step, version, args, hash_of_each_input_file)
```

This makes `put` idempotent: putting the same logical run twice produces the same
uid, and the second insert is a no-op. It also kills a class of bugs: re-running
`scan | put` after a crash does not duplicate work; loop-backs (summarize emitting
new fetch targets that resolve to URLs already fetched) collapse cleanly.

Crucially, this gives free staleness detection. When the profile file changes, its
hash changes, so every eval candidate gets a new uid — `scan eval` naturally surfaces
every node whose eval is stale, without any external "invalidate" trigger.

### Queue interface

```python
class Queue:
    def put(self, candidate: Candidate) -> str: ...           # returns uid; idempotent
    def claim(self, step: str, worker_id: str) -> Item | None: ...
    def mark_done(self, uid: str, output_uris: list[str]): ...
    def mark_error(self, uid: str, reason: str, retryable: bool): ...
    def pending(self, step: str) -> list[Item]: ...
```

`claim()` is the critical operation: it atomically transitions an item from
`pending` to `claimed`, preventing two workers from processing the same item.

### Queue persistence — SQLite as an append-only event log

State is derived from an append-only event log. No rows are ever updated or deleted.
This preserves the audit trail and matches the spirit of the current JSONL format —
just unified across nodes and steps.

```sql
CREATE TABLE events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,  -- global ordering
    uid       TEXT NOT NULL,    -- content-addressed item id
    node_id   TEXT NOT NULL,
    step      TEXT NOT NULL,    -- 'fetch' | 'summarize' | 'eval' | ...
    event     TEXT NOT NULL,    -- 'put' | 'claimed' | 'done' | 'error_retry' | 'error_abort'
    ts        TEXT NOT NULL,
    args        TEXT,           -- JSON dict (put event)
    files       TEXT,           -- JSON list of input vault URIs (put event)
    output_uris TEXT,           -- JSON list (done event)
    worker_id   TEXT,
    detail      TEXT
);

CREATE INDEX idx_events_step_uid ON events (step, uid, id);
```

Current state of an item = its latest event. Pending items for a step:

```sql
SELECT uid, args, files
FROM events
WHERE step = 'fetch'
  AND id IN (SELECT MAX(id) FROM events WHERE step = 'fetch' GROUP BY uid)
  AND event IN ('put', 'error_retry');
```

Per-node history (equivalent to today's `cat fetch.jsonl`):

```sql
SELECT * FROM events WHERE node_id = ? ORDER BY id;
```

Atomic claim is a single transaction: SELECT a pending uid, INSERT a `claimed` event.
SQLite serializes writes, so two workers racing each execute sequentially — the
second finds the item already claimed and backs off.

The per-node JSONL files become *views* over the global log, regenerated on demand.
The global log is the source of truth.

---

## Runner

The runner's job shrinks to: **drain the queue, respect rate limits, stop cleanly.**

```python
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
            item = await self.queue.claim(step.name, worker_id=...)
            if item is None:
                if self._all_quiescent():
                    return
                await asyncio.sleep(POLL_INTERVAL)
                continue
            await step.rate_limiter.acquire()
            try:
                result = await step.work(item, self.vault)
                self.queue.mark_done(item.uid, result.output_uris)
            except RetryableError as e:
                self.queue.mark_error(item.uid, str(e), retryable=True)
            except FatalError as e:
                self.queue.mark_error(item.uid, str(e), retryable=False)
```

The runner does **not** trigger downstream work. It does not call `scan` or `put`.
A run finishing simply marks the queue done; whether new work becomes doable is
something the next `scan` invocation discovers. This is the rule that keeps
intent and execution separated.

### Rate limiting

One `RateLimiter` per external resource (OpenRouter, DDG, SIREN), shared across all
steps that hit it. Token bucket with configurable rate and burst. This is the right
granularity: OpenRouter's quota applies to all LLM steps combined, not per step.

---

## How the current pipeline maps to this model

The existing `fetch → summarize → eval` chain becomes three steps, each with its own
`scan`:

- **fetch** — `scan` reads pending targets (today's open entries in `fetch.jsonl`,
  tomorrow's `targets/` log). Work fetches the URL, writes raw data to the vault.
- **summarize** — `scan` finds `(node, raw_file)` pairs with no summary at the
  current summarizer version. Work calls the LLM, writes `sum_*.json`. New targets
  emitted by the summary land in the `targets/` log, which fetch will pick up on its
  next `scan`.
- **eval** — `scan` finds `(node, latest_sum, active_profile)` triples with no
  matching eval. Work calls the LLM, writes `eval_*.json`.

The current "fetch already done, retry summarize" branch (the `if` inside
`enrich_step()`) disappears: `scan summarize` includes any raw_file lacking a
summary, regardless of whether fetch ran in this session or last week. The
state-machine drawing in `pipeline.py:1-13` is replaced by "look at the event log."

The "loop-back" cycle (summarize → new_targets → fetch) stops being a special case.
Summarize writes `new_targets` to the targets log; the next `scan fetch` sees them.
No queue-to-queue plumbing.

---

## CLI surface

The four core commands map to the four stages. Each is independently useful.

```bash
anpe scan <step>                       # list candidates as JSON, one per line
anpe filter <expr>                     # stdin → stdout, drop non-matching
anpe put                               # stdin → queue
anpe run [--step=...] [--budget=...]   # drain queue, optionally limited

# Convenience compositions:
anpe schedule <step> [--filter=expr]   # = scan | filter | put
anpe step <step> [--filter=expr]       # = scan | filter | put | run
```

The convenience wrappers exist because the most common user motion is
"schedule and run eval on promising nodes." But the four-stage form is always
available for inspection and ad-hoc work.

---

## Design choices and alternatives

### Why not Make / DVC?

Make and DVC handle staleness propagation beautifully but cannot express:
- "rate-limit OpenRouter across all LLM calls"
- "10 parallel async workers per step"
- "filter candidates by current eval score before scheduling"

The first two are why we need a queue and a runner at all. The third is why we need
`filter` as a first-class stage. `scan` borrows the Make idea (derive candidates
from current state); the rest of the pipe handles what Make does not.

### Why not push from each step's output?

The earlier draft of this spec had each step's `work()` write directly to a
downstream queue. Three problems:
- Couples each step to the topology of what comes after it.
- Re-runs and loop-backs need ad-hoc cycle handling.
- "Should this run?" has nowhere to live — the producer always commits.

`scan` decouples discovery from production. The producer just writes its output and
stops; discovery is a separate, idempotent, inspectable function.

### Why content-addressed uids

- Idempotent `put`: re-running `scan | put` after a crash is safe.
- Free staleness detection: changing the profile file changes every eval uid.
- Cycle safety: summarize emitting a target URL that was already fetched produces
  the same fetch uid; the duplicate `put` is a no-op.
- Cache reuse: `run_hash = uid` means the vault doubles as a result cache.

The cost is computing input hashes on every `scan`. For our scale this is negligible
(file mtimes can be a fast pre-check).

### Filter ergonomics

Plain Python predicate strings, evaluated against the candidate record:

```bash
anpe scan eval --filter "score>=7 and reaction!='discard'"
anpe scan summarize --filter "naf.startswith('62')"
```

No DSL, no config files. If a filter is reused, write it as a shell alias or a
small wrapper script. The line we will not cross: filter does not maintain its own
state. Stateful "skip this node forever" lives in `NodeDir`, exposed through a
context field that filters can read.

### Rate limiting granularity

Per external resource, not per step. `OpenRouterLimiter` is shared by `summarize`
and `eval`; `DDGLimiter` is owned by `fetch`. The runner injects the limiter into
the step at construction time.

---

## Open questions

**Filter language.** Plain Python `eval()` on candidate records is the simplest
thing. But `eval` on user-supplied strings is a footgun. Use `simpleeval` or a
hand-rolled comparison parser? Decide before implementing.

**Where does `scan eval` get the active profile?** Reading from
`anpe.profile.active_profile_file()` at scan time is correct but means scan has a
runtime dependency on the profile module. Alternative: pass `--profile=<path>`
explicitly. Probably both — default to active, allow override.

**Worker crash recovery.** A claimed item whose worker dies stays claimed. Options:
(a) heartbeat events, swept by the runner; (b) reclaim claimed-older-than-N-minutes
on startup; (c) manual `anpe queue release <uid>`. Option (c) is fine for current
scale. Revisit if we ever run unattended.

**Quiescence with loop-backs.** `run` stops when the queue is empty *and* no
workers are in-flight. Loop-back works because `scan` is not run automatically — a
new fetch becoming doable does not auto-enqueue. The user (or a wrapping script)
re-runs `scan | put` if they want another pass. This is intentional: it preserves
the rule that intent is explicit.

**Migrating from JSONL.** Each line of today's `fetch.jsonl` maps to one row in
`events`. Per-node raw files and summarize result files stay on disk unchanged —
only the queue index moves. One-off migration script, write once, never run again.

**Per-node JSONL views.** Today's `fetch.jsonl` is human-readable and grep-able. If
the global log becomes the source of truth, we lose `cat node_xyz/fetch.jsonl`.
Solution: `anpe node history <node_id>` regenerates the per-node view from the
event log. Cheap, always current, no drift.
