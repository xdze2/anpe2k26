# ANPE — Company Discovery & Enrichment Design

Consolidated design doc. Supersedes `company_discovery_design.md` and `enrichment_design.md`.

---

## Goal

Let the user discover companies matching their job search criteria, then enrich each
candidate with real information (what they actually do, their website, recent news).

Example query: *"What companies near Bordeaux are doing AI integration for wine production?"*

SIRENE alone surfaces candidates filtered by NAF code and geography — the user triages
them manually. Enrichment (web fetch + LLM eval) is what makes activity-based queries
possible.

---

## Directory structure

All user-generated data lives under one root so it can be backed up as a single private
git repo.

```
anpe_data/                        ← ANPE_DATA_DIR in .env (default: ./anpe_data)
  profile.md
  companies/
    <siren>_<name_slug>.md        ← one file per company, human-readable view + notes
  logs/
    log_<DATE_ISO>.md             ← chat transcripts
  raw_data/
    <siren>/
      enrichment.jsonl            ← append-only event log, single source of truth
      sirene_<DATE>.json
      sirene_eval_<DATE>.md
      ddg_<DATE>.json
      ddg_eval_<DATE>.md
      website_<DATE>.html
      website_eval_<DATE>.md
      ...
  cache/
    sirene_searches/              ← gitignored (ephemeral, regenerable)
      <city>_<radius>km_<naf_codes>.json
```

**All stored paths are relative to `ANPE_DATA_DIR`.** The SIREN is the only stable key —
`raw_data/<siren>/` uses SIREN alone, never a slug.

---

## Company files

Each company gets one markdown file: `companies/<siren>_<name_slug>.md`. The slug is
decorative (human lookup only), never parsed by the pipeline.

### Frontmatter

```yaml
---
siren: "123456789"
name: Acme Viti-Tech
naf: 62.01Z
status: to_look_at        # to_look_at | discarded | good | very_good
enrichment_status: in_progress  # in_progress | done | discarded
found_via: bordeaux_30km_6201Z_2026-04-29
date_found: 2026-04-29
---
```

`status` is the user's triage verdict on the company. `enrichment_status` controls
the pipeline:

| Value | Meaning |
|---|---|
| `in_progress` | pipeline runs normally |
| `done` | soft marker — "enough for now"; pipeline stops but is resumable |
| `discarded` | negative confirmed; pipeline stops |

`done` is always soft: the user can say "re-check this company" and enrichment resumes
or reruns steps. New data can be added manually at any time.

### Body

Human-readable view generated from the latest eval outputs in `raw_data/<siren>/`,
plus freeform user notes. The `## Notes` section is never overwritten by the pipeline.
The body is regenerated after each eval step that produces new meaningful output.

---

## Search tool

One tool: `search_companies(city, radius_km, naf_codes, page)`.

Internal flow:
1. Geocode `city` → lat/lon (reuse `geocode_city()` from `geo_api.py`)
2. Check cache: `cache/sirene_searches/<city>_<radius>km_<naf_codes>.json` (no TTL —
   SIRENE data is stable). `naf_codes` is the sorted, hyphen-joined list.
3. Cache miss → call SIRENE `/near_point` (lat/lon + radius + NAF codes). Hard error
   if `radius_km > 50` (API limit). Save full results to cache.
4. Create `companies/<siren>_<slug>.md` for each new SIREN (never overwrite existing).
   Append a `sirene_fetch: pending` event to `raw_data/<siren>/enrichment.jsonl`.
5. Return paginated summary to the LLM: ~10 results per page (name, SIREN, NAF,
   address). Page number is an explicit tool argument — the LLM tracks it in context.

The agent must propose NAF codes to the user and wait for confirmation before calling
SIRENE. After returning results it must state explicitly that the filter is by sector
code, not actual activity.

---

## Enrichment pipeline

### Core model: seed → layers

The SIREN is just a seed. Everything else is collected in layers, each using prior
layers as context.

```
seed: siren
  → sirene_fetch   → sirene_<DATE>.json
  → sirene_eval    → sirene_eval_<DATE>.md
  → ddg_search     → ddg_<DATE>.json
  → ddg_eval       → ddg_eval_<DATE>.md
  → website_fetch  → website_<DATE>.html
  → website_eval   → website_eval_<DATE>.md
  → tavily_search  → tavily_<DATE>.json        (quota-gated)
  → tavily_eval    → tavily_eval_<DATE>.md
```

Adding a new source is always the same pattern: fetch step + eval step. No structural
changes needed.

---

### Eval structure — 3 layers

Every eval step produces a single structured output (`EvalOutput`) covering three
sequential questions. Later layers are only filled if earlier ones pass.

**Layer 1 — Data quality**

Did the fetch produce exploitable content?

| Value | Meaning | Action |
|---|---|---|
| `ok` | usable content | proceed to layer 2 |
| `not_found` | 404, empty page, no DDG results | no output file; log event |
| `retryable` | network drop, 429, temporary server error | retry automatically |
| `blocked` | 403, Cloudflare, CAPTCHA | needs a code fix; do not retry |

**Layer 2 — Content value** *(only if layer 1 = `ok`)*

Is there new, relevant information?

| Value | Meaning | Action |
|---|---|---|
| `relevant_new` | relevant and not previously known | write output summary file; proceed to layer 3 |
| `relevant_known` | relevant but already captured | no output file; log event |
| `not_relevant` | content doesn't apply to this company | no output file; implicit discard of this step |

A summary file is only written when `relevant_new`. Content value requires prior eval
outputs as context (passed as `context_files`) to judge what is "new."

**Layer 3 — Match delta** *(only if layer 2 = `relevant_new`)*

Does this new information change the user match assessment? References `profile.md`
at a specific version.

| Value | Meaning | Action |
|---|---|---|
| `no_change` | confirms existing assessment | continue pipeline silently |
| `positive` | raises match confidence | continue; may notify user |
| `negative` | lowers match confidence | stop pipeline; company → `discarded` |
| `unclear` | cannot determine without user input | pause; ask user |

Layer 3 events carry a `profile_version` field (hash or mtime of `profile.md`) so
stale verdicts can be identified when the profile changes.

The pipeline is oriented toward positive matches: few companies will be strong
positives among many negatives. `decide_next_step` continues enrichment aggressively
on positive signals and stops early on confirmed negatives. Thresholds are tuned from
real data — not hardcoded now.

---

### JSONL log format

One JSON object per line, appended on each enrichment event. All paths relative to
`ANPE_DATA_DIR`.

```json
{"ts": "2026-04-29T14:20:00", "step": "sirene_fetch", "status": "pending"}

{"ts": "2026-04-29T14:23:00", "step": "sirene_fetch", "status": "done",
 "source": "agent_auto",
 "output_file": "raw_data/123456789/sirene_2026-04-29.json"}

{"ts": "2026-04-29T14:23:05", "step": "sirene_eval", "status": "done",
 "source": "agent_auto",
 "input_files": ["raw_data/123456789/sirene_2026-04-29.json"],
 "context_files": [],
 "output_file": "raw_data/123456789/sirene_eval_2026-04-29.md",
 "author": {"type": "model", "model": "google/gemini-flash-2.0", "prompt_version": "abc123"},
 "eval": {"l1": "ok", "l2": "relevant_new", "l3": "no_change", "profile_version": "a1b2c3"}}

{"ts": "2026-04-29T14:31:00", "step": "website_fetch", "status": "done",
 "source": "user_request",
 "output_file": "raw_data/123456789/website_2026-04-29.html",
 "eval": {"l1": "blocked"}}
```

`output_file` is absent for `pending` events and when no file was produced (l1 !=
`ok`, or l2 != `relevant_new`). `source` distinguishes automatic from user-triggered
steps. `author` records the eval model and prompt version.

All generated files are kept. For any step, the latest file by timestamp is current.
Old versions are superseded but never deleted — safe to rerun evals with improved
prompts.

---

### Step catalogue

| Step | Source | Cost | Notes |
|---|---|---|---|
| `sirene_fetch` | SIRENE API | free | always first |
| `sirene_eval` | LLM | per-token | base context for all subsequent evals |
| `ddg_search` | DDG HTML scrape | free | best first-pass for small French companies |
| `ddg_eval` | LLM | per-token | extracts candidate URL, LinkedIn snippet |
| `website_fetch` | direct HTTP | free | fails on JS-heavy / Cloudflare sites |
| `website_eval` | LLM | per-token | activity summary + match verdict |
| `tavily_search` | Tavily API | 1000 req/month | only for `to_look_at`; never during bulk discovery |
| `tavily_eval` | LLM | per-token | updated summary + verdict |

Eval steps use a separate cheaper model (not the chat agent). The chat agent and eval
model share no context.

Tavily budget is never spent during bulk discovery — only after the user has expressed
interest in a company.

---

### `enrich_company` dispatcher

```
enrich_company(siren)
  ├── disk_io.load_events(siren)         ← reads enrichment.jsonl
  ├── logic.compute_enrichment_state()   ← events → per-step status dict
  ├── logic.decide_next_step(state)      ← None if done / discarded / no steps left
  ├── steps.run_step(next_step, siren)   ← injected fetch_fn / llm_fn
  └── disk_io.append_event(siren, result)
```

**One step per call.** The agent reports progress, can ask the user whether to
continue, and can abort mid-enrichment. The background worker calls `enrich_company`
in a loop until `decide_next_step` returns `None`.

`decide_next_step` encodes only hard rules: no steps remain, `enrichment_status` is
`done` or `discarded`. Heuristic thresholds (when to stop on `unclear`, how many
`no_change` steps before marking `done`) are deferred until real data is available.

---

### User-triggered steps

The user can trigger a specific step directly (e.g. "look at this URL"). The agent
calls the step runner directly, bypassing the dispatcher. Result is logged identically
(`source: "user_request"`). The dispatcher sees the step as `done` on the next call —
no special-casing.

---

### Background worker

`uv run anpe enrich` — scans all SIRENs in `raw_data/` where
`compute_enrichment_state()` returns at least one `pending` step, then calls
`enrich_company()` for each. `failed` steps (`retryable`) are retried automatically.
`blocked` steps surface for user review.

---

## Module structure

```
anpe/enrichment/
  models.py      — EnrichmentEvent, EvalOutput, enums (pure pydantic / dataclasses)
  logic.py       — compute_enrichment_state, decide_next_step (pure functions, no I/O)
  disk_io.py     — load_events, append_event, write_raw_file, read_raw_file
  steps.py       — run_sirene_fetch, run_sirene_eval, ... (fetch_fn / llm_fn injected)
  dispatcher.py  — enrich_company (wires disk_io + logic + steps)
```

`models.py` and `logic.py` have zero imports from `disk_io.py`. `dispatcher.py` is the
only place that calls both. Tests for `logic.py` never touch the filesystem.

---

## Implementation order

Critical path first — validate data structures and enrichment logic before building
peripheral features:

1. `models.py` — enums, `EnrichmentEvent`, `EvalOutput`
2. `disk_io.py` — JSONL read/write (tests use temp directory)
3. `logic.compute_enrichment_state` — events → state dict (pure, fixture-based tests)
4. `logic.decide_next_step` — state → next step (pure, table-driven tests)
5. `steps.py` — step runners with injected fetch/LLM (mocked in tests)
6. `dispatcher.py` — `enrich_company` integration test (mocked fetch + LLM)

Non-critical (after validation):
- `search_companies` tool (SIRENE API, geocoding, cache, pagination)
- Company `.md` body regeneration
- Real DDG scraper and website fetcher
- Tavily integration
- Background worker CLI
- Agent workflow and dynamic system prompt

---

## Open questions

- Inbox file drop (anti-scrape fallback): needs SIREN reverse-lookup. Deferred.
- Global searches not tied to one company: `raw_data/_global/`? Deferred.
- Automatic `done` heuristic: after how many consistent `positive` evals? Tune from data.
- `unclear` surfacing: write `needs_review` flag to company frontmatter, check at
  session start. Not yet implemented.
