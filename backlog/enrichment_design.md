# Company Enrichment — Design Notes

## Goal

After SIRENE discovery, enrich each company with real information: what they actually do,
their website, recent news, etc. SIRENE alone cannot answer "do they work on AI + wine" —
enrichment is what makes activity-based queries possible.

---

## Core model: seed → layers

The SIREN number is just a seed — a stable identifier. Everything else, including SIRENE
data itself, is collected data organized in layers. Each layer uses the previous layers as
context.

```
seed: siren
  → sirene_fetch   → sirene_<DATE>.json
  → sirene_eval    → sirene_eval_<DATE>.md    (name, location, NAF, ...)
  → ddg_search     → ddg_<DATE>.json
  → ddg_eval       → ddg_eval_<DATE>.md       (candidate URL, LinkedIn snippet)
  → website_fetch  → website_<DATE>.html
  → website_eval   → website_eval_<DATE>.md   (activity summary, worthiness verdict)
  → tavily_search  → tavily_<DATE>.json
  → tavily_eval    → tavily_eval_<DATE>.md
  → ...
```

Adding a new data source is always the same pattern: a fetch step + an eval step.
No structural changes needed.

---

## Data storage

```
anpe_data/raw_data/<siren>/
  enrichment.jsonl               ← append-only event log, single source of truth
  sirene_2026-04-29.json         ← raw SIRENE API response
  sirene_eval_2026-04-29.md
  ddg_2026-04-29.json
  ddg_eval_2026-04-29.md
  website_2026-04-30.html
  website_eval_2026-04-30.md
  website_eval_2026-05-01.md     ← re-ran with improved prompt, old one kept
  ...
```

**All generated files are kept.** For any step, the latest file (by timestamp) is the
current result. Old versions are superseded but not deleted — storage is cheap, and
this makes it safe to re-run evals with improved prompts without losing history.

File paths are **never reconstructed by parsing filenames**. The JSONL log is the only
index — every event records the exact path of the file it produced.

The raw_data directory uses `<siren>` only (no slug) — the SIREN is the stable key,
the slug is decorative.

---

## Every step produces a file

- **Fetch steps** write raw data to `raw_data/<siren>/` and log the path.
- **Eval steps** read one or more input files, write a summary/verdict file, and log
  input paths + output path + author metadata.

```
fetch(siren) → raw file
eval(raw_file, context_files=[...]) → summary file
```

---

## Enrichment state

State is computed on the fly from the JSONL log — no caching needed (files are tiny).

```python
def compute_enrichment_state(siren: str) -> EnrichmentState:
    """Read enrichment.jsonl, return current state of each step."""
    ...
```

Each step has a status:

| Status | Meaning |
|---|---|
| `pending` | queued, not yet run |
| `done` | completed successfully |
| `failed` | error, needs user approval to retry |
| `skipped` | explicitly excluded (e.g. no website exists) |
| `None` | not yet started |

Each `done` eval step also carries a **verdict** (e.g. `useful | no_new_info |
fetch_error | no_web_presence`). `decide_next_step()` reads both status and verdict
to determine what to do next — "done" alone is not enough.

`decide_next_step()` is the single place encoding step ordering and preconditions.
Testable in isolation with a fake state dict.

---

## JSONL log format

One JSON object per line, appended on each enrichment event:

```json
{"ts": "2026-04-29T14:23:00", "step": "sirene_fetch", "status": "done",
 "source": "agent_auto",
 "output_file": "raw_data/123456789/sirene_2026-04-29.json"}

{"ts": "2026-04-29T14:23:05", "step": "sirene_eval", "status": "done",
 "source": "agent_auto",
 "input_files": ["raw_data/123456789/sirene_2026-04-29.json"],
 "context_files": [],
 "output_file": "raw_data/123456789/sirene_eval_2026-04-29.md",
 "author": {"type": "model", "model": "google/gemini-flash-2.0", "prompt_version": "abc123"},
 "verdict": "useful"}

{"ts": "2026-04-29T14:31:00", "step": "website_eval", "status": "done",
 "source": "user_request",
 "input_files": ["raw_data/123456789/website_2026-04-29.html"],
 "context_files": ["raw_data/123456789/sirene_eval_2026-04-29.md",
                   "raw_data/123456789/ddg_eval_2026-04-29.md"],
 "output_file": "raw_data/123456789/website_eval_2026-04-29.md",
 "author": {"type": "human"},
 "verdict": "useful"}
```

`source` distinguishes automatic steps from user-triggered ones — audit trail only.
`author` records who produced the eval: a model (with version) or a human.
Context accumulates across layers: later evals reference earlier eval outputs.

---

## Enrichment steps (ordered)

0. **`sirene_fetch`** — fetch raw SIRENE data for this SIREN. Always the first step.
1. **`sirene_eval`** — LLM extracts name, address, NAF, size. Base context for all subsequent evals.
2. **`ddg_search`** — DuckDuckGo HTML scrape. Free, zero quota. Best first-pass for small French companies.
3. **`ddg_eval`** — LLM reads DDG results + sirene_eval context → extracts candidate website URL, LinkedIn snippet. Outcome: a URL, or `"none"`.
4. **`website_fetch`** — Direct HTTP fetch of homepage + `/about`. Free. Fails on JS-heavy or Cloudflare-protected sites.
5. **`website_eval`** — LLM reads HTML + prior eval context → activity summary, worthiness verdict, next targets.
6. **`tavily_search`** — Fallback for hard cases, or news/forum queries. 1000 req/month quota — use only for `to_look_at` companies, not bulk discovery.
7. **`tavily_eval`** — LLM reads Tavily results + prior context → updated summary, verdict.

Steps are not strictly sequential for all cases: `tavily_search` can be triggered
independently (e.g. "find recent news about DataVin") without completing prior steps.

---

## `enrich_company` — dispatcher

```
enrich_company(siren)
  ├── compute_enrichment_state(siren)   ← reads enrichment.jsonl
  ├── decide_next_step(state)           ← None if all done/failed/skipped
  ├── run_step(next_step, siren)
  └── append_jsonl(siren, result)
```

**One step per call.** This gives the agent control: it can report progress, ask the user
whether to continue, or abort mid-enrichment. The background worker just calls
`enrich_company` in a loop until `decide_next_step` returns `None`.

---

## User-triggered enrichment

The user can trigger specific steps directly:

> "Look at the site URL https://..."

The agent calls the step tool directly (bypassing the dispatcher), passing the
user-supplied URL as an explicit override. Result is logged to JSONL identically
(`source: "user_request"`). The dispatcher sees the step as `done` on the next call —
no special-casing.

---

## Background worker

The worker scans all SIRENs in `raw_data/` where `compute_enrichment_state()` returns
at least one `pending` step, then calls `enrich_company()` for each.

Triggered via a separate CLI command (`uv run anpe enrich`) or on startup.
`failed` steps are not retried automatically — they surface for user review.

**Open design question:** a pure Python loop cannot handle ambiguous results or
freeform inbox files needing company identification. An autonomous LLM agent would
handle these naturally but introduces runaway API / quota risks. Not designed yet —
the interactive enrichment path comes first.

---

## Quota management

| Source | Cost | When to use |
|---|---|---|
| SIRENE API | free | always, first step |
| DuckDuckGo HTML | free | always, after SIRENE |
| Direct HTTP fetch | free | after website URL identified |
| Tavily | 1000 req/month | `to_look_at` companies only, or user-triggered |
| LLM eval | per-token | every fetch step; use a cheap/fast model |

Tavily budget must not be spent during bulk discovery — only after the user has
expressed interest in a company. The eval model does not need to be the same as the
chat agent — a cheaper model is fine.

---

## Open questions

- LLM summarization: at what point does a final human-readable summary get written to
  `companies/<siren>.md`? After each eval step, or after all steps complete?
- `companies/<siren>.md` role: is it a generated view (from latest eval outputs) or
  does it remain the place for human notes? Probably both, but the separation needs
  to be explicit.
- General searches (news, forums) not tied to one company: same JSONL structure but
  stored where? Possibly `raw_data/_global/`.
- Manual inbox file drop (for anti-scrape fallback): needs a SIREN reverse-lookup to
  link freeform files to a known company. Deferred — not a priority now.
