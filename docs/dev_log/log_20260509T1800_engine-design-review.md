# Engine design review — broad-view pass

Date: 2026-05-09

## What happened

Stepped back from line-level cleanup and took a broad view of the engine
design after the data-engine refactor and partial cleanup. No code changed
this session — the output is an updated [todo.md](../../todo.md).

## Findings

The `scan | filter | put | run` decomposition holds up well. Content-addressed
UIDs + write-once vault give idempotent re-puts and free staleness; the SQLite
event log carries everything cleanly.

Six things flagged:

1. **The step graph is implicit.** Every `scan()` opens with
   `for ev in queue.done_events(_UPSTREAM):` where `_UPSTREAM` is a private
   string constant. The pipeline shape exists nowhere as data — only by grep.
   Lift to `Step.inputs_from`. Highest leverage.

2. **The `_bootstrap` sentinel reveals a missing concept.** `node_id` is doing
   two jobs (partition key, entity reference). Process-level steps have no
   entity. Make it a first-class `Step.scope: Literal["node", "global"]`
   attribute so future global steps don't need more underscore sentinels.

3. **`scan()` returning a list is the wrong shape for budgets.** Three steps
   already paper over with `count: int = 10`. Generator makes scan lazy and
   removes the half-baked `count` flag.

4. **Budget should be per-rate-gate, not per-item.** "Spend at most 50 LLM
   calls" maps to gate acquisitions, not items processed. Item-budget on
   `run --budget=N` doesn't reflect what the user actually wants to bound.

5. **No driver for "run the whole thing."** Today: 5 sequential `anpe step`
   commands per session. Once the graph is explicit and budgets are
   gate-aware, an `anpe loop` command falls out almost for free.

6. **Smaller things:** `node_id` duplicated on Candidate and inside `args`;
   `# type: ignore[type-arg]` noise; `done_events` reads grow linearly with
   corpus size (premature to fix).

## Suggested order

`inputs_from` → generator scan → `scope` rename → gate budgets → `anpe loop`
→ small cleanups. First three are independent and small; #4+#5 are the
"this is what I actually wanted" payoff.

Full breakdown with file references in [todo.md](../../todo.md), reorganized
by priority (P1 = the five design moves, P2 = leftover prior items, P3 =
small cleanups, P4 = flagged-not-yet-worth-fixing).
