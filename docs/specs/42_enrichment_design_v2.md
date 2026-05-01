# Enrichment Design

Implementation doc. Translates `20_principles.md` into file structures, data formats,
function signatures, and module layout. Supersedes the previous version of this file.

---

## Directory structure

All user data lives under one root — a private git repo.

```
anpe_data/                         ← ANPE_DATA_DIR in .env (default: ./anpe_data)
  profile.md
  companies/
    node<SIREN>/                   ← one directory per node
      summary.md                   ← human-readable view + frontmatter + notes
      enrichment.jsonl             ← history: fetch + eval events, append-only
      queue.jsonl                  ← intent: proposed fetch targets, append-only
      raw_data/
        sirene_<DATE>.json
        ddg_<DATE>.json
        website_<DATE>.html
        tavily_<DATE>.json
        <step>_eval_<DATE>.md      ← eval output, only written when relevant+new
        ...
  logs/
    log_<DATE_ISO>.md              ← chat transcripts
  cache/
    sirene_searches/               ← gitignored, regenerable
      <city>_<radius>km_<nafs>.json
```

All paths inside JSONL files are relative to `ANPE_DATA_DIR`. The SIREN is the only
stable key — it appears in the directory name and nowhere else structurally.

---

## Node structure

### `summary.md`

Frontmatter holds structured state. Body is a human-readable summary regenerated after
each eval that produces new relevant information. The `## Notes` section is freeform
and never overwritten by the pipeline.

```yaml
---
siren: "123456789"
name: Acme Viti-Tech
naf: 62.01Z
status: to_look_at        # to_look_at | discarded | good | very_good
found_via: bordeaux_30km_6201Z_2026-04-29
date_found: 2026-04-29
---
```

`status` is the user's triage verdict. Set by the user directly, or set to `discarded`
by the pipeline on a clear negative eval. The user can always override.

Body structure (generated, except Notes):
```markdown
## Summary
<LLM-generated, relative to user profile>

## Next fetch candidates
<latest queue proposals — informational, not parsed>

## Notes
<freeform, never overwritten>
```

### `enrichment.jsonl`

Append-only log of everything that has happened to this node. Each line is one event.

```jsonl
{"ts": "2026-04-29T14:20:00", "step": "sirene_fetch", "fetch_status": "ok",
 "source": "agent_auto",
 "output_file": "companies/node123456789/raw_data/sirene_2026-04-29.json"}

{"ts": "2026-04-29T14:20:05", "step": "sirene_eval",
 "source": "agent_auto",
 "input_file": "companies/node123456789/raw_data/sirene_2026-04-29.json",
 "output_file": "companies/node123456789/raw_data/sirene_eval_2026-04-29.md",
 "author": {"model": "google/gemini-flash-2.0", "prompt_version": "abc123"},
 "eval": {"l1": "relevant", "l2": "new", "l3": "no_change"},
 "profile_version": "a1b2c3"}

{"ts": "2026-04-29T14:31:00", "step": "website_fetch", "fetch_status": "blocked",
 "source": "user_request",
 "target": "https://acmevititech.fr"}
```

Fields:
- `ts` — ISO timestamp
- `step` — step name (see step catalogue)
- `source` — `agent_auto` | `user_request`
- `fetch_status` — only on fetch steps: `ok` | `not_found` | `retryable` | `blocked`
- `target` — URL or query used (fetch steps)
- `output_file` — written only when a file was produced
- `eval` — only on eval steps: `{l1, l2, l3}` with layer values
- `profile_version` — hash or mtime of `profile.md` at eval time (eval steps only)
- `author` — model and prompt version (eval steps only)

`output_file` is absent when no file was produced (fetch failed, or eval l1/l2 stopped
early). All raw files are kept — the latest by timestamp is current.

### `queue.jsonl`

Append-only log of proposed fetch targets. Last status per `(step, target)` pair is
current state. Written by `next_fetch_target` after the fixed steps are done.

```jsonl
{"ts": "2026-04-29T14:21:00", "status": "proposed", "step": "website_fetch",
 "target": "https://acmevititech.fr",
 "rationale": "URL found in DDG snippet",
 "info_gain": "likely has activity description and headcount"}

{"ts": "2026-04-29T14:21:00", "status": "proposed", "step": "website_fetch",
 "target": "https://linkedin.com/company/acme-viti-tech",
 "rationale": "LinkedIn URL in DDG results",
 "info_gain": "headcount, founding year, employee profiles"}

{"ts": "2026-04-29T14:35:00", "status": "done", "step": "website_fetch",
 "target": "https://acmevititech.fr"}
```

Statuses: `proposed` → `done` | `skipped`. A target is pending if its latest status
is `proposed`. The dispatcher picks the top pending entry.

---

## Search tool

`search_companies(city, radius_km, naf_codes, page)` — agent-callable tool.

```
1. geocode_city(city) → lat, lon
2. cache_key = f"{city}_{radius_km}km_{'–'.join(sorted(naf_codes))}"
   check cache/sirene_searches/<cache_key>.json  (no TTL — SIRENE data is stable)
3. cache miss → call SIRENE /near_point(lat, lon, radius_km, naf_codes)
   hard error if radius_km > 50
   save full response to cache
4. for each new SIREN (not already in companies/):
     create companies/node<SIREN>/
     write summary.md with frontmatter (status: to_look_at)
     create empty enrichment.jsonl and queue.jsonl
5. return paginated slice (~10 entries): name, SIREN, NAF, address
   page is an explicit argument — the agent tracks it in context
```

The agent must propose NAF codes and wait for user confirmation before calling this
tool. After returning results it must state that the filter is by sector code, not
actual activity.

---

## Enrichment pipeline

### Dispatcher — `enrich(node_id)`

One step per call. Returns the eval result, or a fetch status if the fetch failed,
or `None` if enrichment is complete.

```python
def enrich(node_id: str) -> EvalOutput | FetchStatus | None:
    events = disk_io.load_events(node_id)          # reads enrichment.jsonl
    queue  = disk_io.load_queue(node_id)           # reads queue.jsonl
    state  = logic.compute_node_state(events, queue)

    if logic.is_complete(state):                   # discarded or no targets left
        return None

    # Fixed steps: SIRENE then DDG, checked against enrichment history
    fixed = logic.next_fixed_step(state)
    if fixed:
        target = fixed
    else:
        # LLM proposes targets if queue is empty
        if not state.has_pending_targets:
            proposals = next_target.propose(state, profile)
            disk_io.append_queue_entries(node_id, proposals)
            state = logic.compute_node_state(
                disk_io.load_events(node_id),
                disk_io.load_queue(node_id)
            )
        target = logic.top_pending_target(state)
        if target is None:
            return None

    raw, fetch_status = steps.fetch(target)
    disk_io.append_event(node_id, fetch_event(target, fetch_status, raw))

    if fetch_status != FetchStatus.ok:
        return fetch_status                        # caller handles retryable/blocked

    eval_result = steps.run_eval(raw, state, profile)
    disk_io.append_event(node_id, eval_event(target, eval_result))
    disk_io.mark_queue_done(node_id, target)       # appends "done" to queue.jsonl

    if eval_result.l2 == "new":
        summary = steps.regenerate_summary(state, eval_result, profile)
        disk_io.write_summary(node_id, summary)

    if eval_result.l3 == "discard":
        disk_io.set_status(node_id, "discarded")

    return eval_result
```

### `next_fixed_step`

Pure function. Returns `"sirene_fetch"` if SIRENE has not been fetched yet, then
`"ddg_search"` if DDG has not been fetched yet, then `None`. Checks `enrichment.jsonl`
history only.

### `next_fetch_target` (LLM call)

Called when fixed steps are done and the queue has no pending entries. Receives the
full node state (all eval outputs, current summary, fetch history) and the list of
available tools with their costs. Returns a ranked list of `QueueEntry` objects.

The LLM uses cost information in the prompt to rank candidates — no hardcoded ordering
logic beyond the fixed steps.

### User-triggered steps

The user can request a specific fetch ("look at this URL"). The agent calls
`steps.fetch(target)` and `steps.run_eval(...)` directly, bypassing the dispatcher.
Events are logged identically with `source: "user_request"`. The dispatcher sees the
step as done on the next call — no special-casing needed.

---

## Fetch

Each fetch tool has the same interface:

```python
def fetch_<source>(target: str) -> tuple[bytes | str, FetchStatus]: ...
```

`FetchStatus` is determined by the tool itself — no LLM involved.

| Status      | Meaning                       | Dispatcher action    |
| ----------- | ----------------------------- | -------------------- |
| `ok`        | usable content returned       | proceed to eval      |
| `not_found` | 404, empty result, no hits    | log and move on      |
| `retryable` | network error, rate limit     | retry later          |
| `blocked`   | Cloudflare, CAPTCHA           | surface to user      |

---

## Eval — 3 layers

```python
def run_eval(raw, node_state: NodeState, profile: str) -> EvalOutput: ...
```

LLM call. Receives raw fetch output, the full node state (prior evals + summary),
and the user profile. Returns a structured `EvalOutput`.

**Layer 1 — Content value**

| Value          | Meaning                         | Action  |
| -------------- | ------------------------------- | ------- |
| `relevant`     | content applies to this company | proceed |
| `not_relevant` | wrong company or empty content  | stop    |

**Layer 2 — New information** *(only if l1 = `relevant`)*

| Value   | Meaning              | Action                              |
| ------- | -------------------- | ----------------------------------- |
| `new`   | not previously known | proceed — regenerate summary        |
| `known` | already captured     | stop — no update                    |

**Layer 3 — Match delta** *(only if l2 = `new`)*

| Value       | Meaning                             | Action                             |
| ----------- | ----------------------------------- | ---------------------------------- |
| `no_change` | consistent with current verdict     | continue silently                  |
| `revisit`   | new signal that could shift verdict | queue for user review              |
| `discard`   | clearly negative signal             | set status=discarded; stop         |

`revisit` carries a reason string: the specific signal that warrants attention.
All layer 3 events record `profile_version` so stale verdicts can be identified
when the profile changes.

---

## Step catalogue

| Step | Source | Cost |
|---|---|---|
| `sirene_fetch` | SIRENE API | free — always first |
| `sirene_eval` | LLM (eval model) | per-token |
| `ddg_search` | DDG HTML scrape | free — always second |
| `ddg_eval` | LLM (eval model) | per-token |
| `website_fetch` | direct HTTP | free — may be blocked |
| `website_eval` | LLM (eval model) | per-token |
| `tavily_search` | Tavily API | 1000 req/month — post-interest only |
| `tavily_eval` | LLM (eval model) | per-token |

Eval steps use a dedicated cheaper model. The chat agent and eval model share no
context — the agent reads eval output files, not eval model context.

Tavily is never called during bulk discovery. Only after `status: good` or
`very_good`.

---

## Module structure

```
anpe/enrichment/
  models.py       — EnrichmentEvent, QueueEntry, EvalOutput, FetchStatus, NodeState
                    (pure pydantic / dataclasses, no I/O)
  logic.py        — compute_node_state(events, queue) → NodeState
                    next_fixed_step(state) → str | None
                    top_pending_target(state) → QueueEntry | None
                    is_complete(state) → bool
                    (pure functions, no I/O — fully unit-testable)
  disk_io.py      — load_events, append_event
                    load_queue, append_queue_entries, mark_queue_done
                    write_raw_file, read_raw_file
                    write_summary, set_status
  fetchers.py     — fetch_sirene, fetch_ddg, fetch_website, fetch_tavily
  eval.py         — run_eval(raw, state, profile) → EvalOutput  (LLM call)
                    regenerate_summary(state, eval_result, profile) → str  (LLM call)
  next_target.py  — propose(state, profile) → list[QueueEntry]  (LLM call)
  dispatcher.py   — enrich(node_id) — wires all modules together
```

`models.py` and `logic.py` have zero I/O imports. Tests for `logic.py` never touch
the filesystem. `dispatcher.py` is the only place that calls both `disk_io` and LLM
modules.

---

## Implementation order

Critical path — validate data structures and core logic before building I/O or LLM
calls:

1. `models.py` — all enums and dataclasses
2. `disk_io.py` — JSONL read/write, summary read/write (tests use tmp directory)
3. `logic.compute_node_state` — events + queue → NodeState (pure, fixture-based tests)
4. `logic.next_fixed_step` + `logic.top_pending_target` (pure, table-driven tests)
5. `fetchers.py` — one fetcher at a time, starting with SIRENE (inject HTTP client)
6. `eval.py` — run_eval with injected LLM (mocked in tests)
7. `next_target.py` — propose with injected LLM (mocked in tests)
8. `dispatcher.py` — integration test with mocked fetchers + LLM

Non-critical (after core works):
- `search_companies` tool (SIRENE search, geocoding, cache, node creation)
- Summary regeneration
- Background worker CLI (`uv run anpe enrich`)
- Agent tool wrappers
- Tavily integration

---

## Open questions

- **Global searches** — web queries not tied to a specific SIREN (e.g. sector news).
  Possible home: `raw_data/_global/`. Deferred.
- **Automatic pipeline stop heuristic** — after how many consistent `no_change` evals
  should enrichment stop automatically? Tune from real data.
- **`revisit` queue persistence** — where are queued revisit items stored between
  sessions? Possibly a `revisit.jsonl` at the `anpe_data/` root, or a flag in
  `summary.md` frontmatter. Not yet decided.
- **Inbox file drop** — manually dropping a file into the node directory as a data
  source (anti-scrape fallback). Needs design. Deferred.
