---
status: draft
---

# Future — design questions parked for later

This file collects design moves that came out of broad-view review sessions
on the data engine, but that are deliberately **not** being acted on now.
Each one is a real question with a sketched-out answer; none is urgent
enough to interrupt the current trajectory.

The ordering does not imply priority. Revisit when concrete pressure from
real use makes one of these load-bearing.

---

## Phase as a Step attribute

**The observation.** From a user's perspective there are 4 phases of work:

1. bootstrap — produce a company listing
2. fetch — pull raw data about a company (from any source)
3. llm — summarize the raw data, identify new targets, score against the profile
4. user review — surface to the human, capture a reaction

The current engine has 6 concrete steps: `bootstrap`, `fetch_siren`,
`fetch_ddg`, `summarize_ddg`, `eval`, `review`. The mismatch is that the
extra steps reflect *implementation* choices (which API, which prompt
template), not *phases* of work.

**Why not collapse all the way.** The instinct is to make `fetch` one step
parameterized by `tool`, and `llm` one step parameterized by what it's
doing. Four things resist that:

- **Rate gates differ per tool.** DDG, SIREN, and Mistral all have
  different limits. Today the runner picks `step.rate_gate` once; with one
  unified `fetch` step, the gate has to be selected from `args` at
  runtime, which the current rate-gate design does not support cleanly.

- **Versions get tangled.** `summarize_ddg.version` is currently a hash
  over the DDG-specific prompt. Tweaking that prompt should not invalidate
  LinkedIn summaries (when LinkedIn lands). Either the version covers
  both (over-invalidation) or the version becomes `(step, tool)` —
  which is just per-tool steps with extra ceremony.

- **`scan` shape differs by tool.** `fetch_siren.scan` reads bootstrap
  listings; `fetch_ddg.scan` reads `fetch_siren` done events. They have
  different upstreams. A unified `fetch.scan` has to dispatch by tool
  internally — at which point you have recreated per-tool steps inside
  one step.

- **Error semantics differ.** `FetchBlockedError` is meaningful for DDG
  scraping; nonsense for the SIREN public API.

For **summarize + eval** specifically: eval re-runs when the **profile**
changes; summarize does not. Bundling them means every profile edit
re-runs summarize too, wasting LLM calls. They are two cache units even
though they feel like "one LLM phase" to the user.

**The proposal.** Keep per-tool steps as the **execution unit** (because
version, gate, scan-shape, and error-mode all want to vary per tool). Add
a `phase` attribute that names the user-facing grouping:

```python
class FetchDdgStep:     name = "fetch_ddg";     phase = "fetch"
class FetchSirenStep:   name = "fetch_siren";   phase = "fetch"
class SummarizeDdgStep: name = "summarize_ddg"; phase = "llm"
class EvalStep:         name = "eval";          phase = "llm"
class ReviewStep:       name = "review";        phase = "review"
class BootstrapStep:    name = "bootstrap";     phase = "bootstrap"
```

What this buys:

- `anpe loop` walks phases, not individual steps — matches the user's
  mental model.
- `anpe scan --phase=fetch` lists pending candidates across DDG + SIREN.
- Adding LinkedIn = `Step(name="fetch_linkedin", phase="fetch")` plus a
  matching `summarize_linkedin` in `phase="llm"`. No engine change.
- The 4-phase view becomes the surface; the per-tool DAG stays the
  substrate. Both are true at the same time.

**When to actually do this.** When a second fetch tool (or LLM prompt
variant) is concretely landing. Today there is exactly one fetch tool that
matters operationally (`fetch_ddg` after `fetch_siren`). Adding `phase`
preemptively is a knob with no setting.

---

## Effort, cost, and per-candidate budgets

**The observation.** This is an exploration engine over thousands of
candidates. The vision doc says it explicitly: "enrichment has a cost —
in time, in API calls, in noise — so it can't be applied blindly to every
candidate." Today the only triage mechanisms are *capability* (`scan`
checks inputs exist) and *hardcoded scan flags* (`--min-score=maybe`).
There is no continuous quantity that says "this node deserves more
investment." That is missing.

**The intuition that came up.** Each step has a **cost** (how much effort
it consumes), each candidate carries a **budget** (how much it is worth
spending). A candidate gets enriched only if its budget can pay the next
step's cost.

**Where the intuition is right.**

- It is the right shape for a job-search funnel: thousands of candidates
  cheap-fetched, hundreds expensive-fetched, dozens LLM-evaluated, a
  handful surfaced to the user.
- It composes with the **per-rate-gate session budget** (see todo.md P1).
  Two different scopes:
  - Session budget: "spend at most 50 LLM calls today, total."
  - Candidate budget: "this node is worth at most 3 LLM calls before I
    give up on it."
  Both are useful; they answer different questions.
- It gives the LLM eval verdict a natural lever: `discard` zeroes the
  budget, `enrich` raises it.

**Where it splits into two distinct concepts.**

- **Step cost** is engine-side and mostly static. "Eval costs 1 LLM
  call." This maps cleanly onto the rate-gate concept already proposed.
  Most steps cost 1 of one gate. Declared on the step class:
  `cost_per_gate: dict[str, int]`.

- **Candidate budget** is data-side and dynamic. "This node has 5
  LLM-credits left." It wants to be derived from event-log state, not
  stored separately. It changes from three sources:
  - Initial allocation at bootstrap (every node starts with budget B).
  - Verdict-driven changes: eval `good` raises it, `discard` zeroes it.
  - User reaction-driven changes: "interesting" tops it up.

  Concretely: each step's outputs include a `verdict` enum
  (`continue` / `boost` / `freeze` / `kill`) and a fixed table maps
  verdict to budget delta. Steps stay declarative; budget logic stays in
  one place.

**The simpler thing to do first: a node lifecycle.**

Before introducing a continuous budget, the discrete version may be
enough. The eval verdicts already produce four labels:
`good`, `maybe`, `enrich`, `discard`. These map naturally onto a
three-state node lifecycle:

- **alive** — keep enriching
- **frozen** — paused (e.g. `maybe` after a couple of cycles)
- **dead** — stop spending on this node (`discard`, or user
  `not_interesting`)

`scan` filters out frozen and dead nodes by default. State is derived
from the latest eval verdict and the latest user reaction. No continuous
budget needed.

This is the 80% solution and it is almost free given the verdicts already
exist. It gives the triage the engine is missing, while staying discrete,
inspectable, and debuggable.

**When to add the continuous budget.** Only if the discrete lifecycle
turns out to be too coarse — e.g. "this node was `maybe` once, give it
exactly 2 more fetch attempts before freezing." If that becomes a felt
need, the cost/budget pair lands on top of the lifecycle without
disturbing it.

**The thing to be cautious about.** Don't introduce budgets before there
is a concrete policy you want to enforce. A budget without a policy is a
knob with no setting. The policy needs to come from real use of the
exploration loop, not from imagining it.

---

## Status

Both items are **deferred**. The current trajectory (todo.md P1: explicit
step graph, scope, generator scan, gate budgets, `anpe loop`) does not
require either of these. They become live questions when:

- A second fetch tool or LLM prompt variant is actually landing
  (→ revisit `phase`).
- The exploration loop is in regular use and triage feels missing
  (→ revisit lifecycle, then budget).

Until then, this file is the parking lot.
