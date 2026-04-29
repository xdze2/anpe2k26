# Company Enrichment — Design Notes

## Goal

After SIRENE discovery, enrich each company with real information: what they actually do,
their website, recent news, etc. SIRENE alone cannot answer "do they work on AI + wine" —
enrichment is what makes activity-based queries possible.

---

## Data storage

```
anpe_data/raw_data/<siren>_<slug>/
  enrichment.jsonl              ← append-only event log, single source of truth
  ddg_<DATE>.json               ← raw DDG results
  website_homepage_<DATE>.html  ← raw HTML capture
  tavily_<DATE>.json            ← raw Tavily results
```

The company `.md` file contains only SIRENE data + human-readable notes.
No enrichment state is cached there — state is always computed from `enrichment.jsonl`.

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
| `None` | not yet decided |

`decide_next_step()` is the single place encoding step ordering and preconditions
(e.g. `website_fetch` cannot run if `website_url` is `"none"`). Testable in isolation
with a fake state dict.

---

## JSONL log format

One JSON object per line, appended on each enrichment event:

```json
{"ts": "2026-04-29T14:23:00", "step": "ddg_search", "status": "done", "source": "agent_auto", "output_file": "ddg_2026-04-29.json"}
{"ts": "2026-04-29T14:23:05", "step": "website_fetch", "status": "failed", "source": "agent_auto", "error": "timeout"}
{"ts": "2026-04-29T14:31:00", "step": "website_fetch", "status": "done", "source": "user_request", "output_file": "website_homepage_2026-04-29.html"}
```

`source` distinguishes automatic steps from user-triggered ones — audit trail only,
does not affect state computation.

---

## Enrichment steps (ordered)

0. **`scan_inbox`** — check `anpe_data/inbox/<siren>_*` for manually dropped files. Runs first; if a file is found it is moved to `raw_data/` and logged. Skips automatically if inbox is empty for this SIREN.
1. **`ddg_search`** — DuckDuckGo HTML scrape: grab LinkedIn snippet + candidate website URL. Free, zero quota. Best first-pass for small French companies.
2. **`website_identify`** — Confirm or resolve the website URL from DDG results. Outcome: a URL, or `"none"` (freelancer, dissolved company, no web presence).
3. **`website_fetch`** — Direct HTTP fetch of homepage + `/about`. `requests` + `BeautifulSoup`. Free, covers most simple static sites. Fails on JS-heavy or Cloudflare-protected sites.
4. **`tavily_search`** — Fallback for hard cases, or for news/forum queries not tied to a specific URL. 1000 req/month quota — use only for `to_look_at` companies, not bulk discovery.

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
user-supplied URL as an explicit override:

```python
def fetch_website(siren: str, url: str | None = None) -> StepResult:
    resolved_url = url or get_url_from_state(siren)
    ...
```

Result is logged to JSONL identically (`source: "user_request"`). The dispatcher
sees the step as `done` on the next call — no special-casing.

### Manual file drop (anti-scrape fallback)

For sites with hard anti-scrape protection (LinkedIn, some corporate intranets),
the user can manually export content and drop it into a watched inbox directory:

```
anpe_data/inbox/
  <siren>_<anything>.md     ← manually copied/exported content
  <siren>_<anything>.txt
  <siren>_<anything>.html
```

The file naming convention (`<siren>_*`) is the only required structure — the rest
is freeform. On the next agent turn (or background worker pass), a `scan_inbox()`
step detects new files, moves them to `raw_data/<siren>_<slug>/`, and logs the event
to `enrichment.jsonl` with `source: "user_manual_drop"`.

This covers: LinkedIn page exports, Notion exports, browser "Save as", any manual
copy-paste saved to a file. No special tooling needed — the user is the scraper.

Freeform files (no SIREN prefix, e.g. a news article copy-pasted about an unknown
company) are also accepted. The agent tries to identify the company from the content
and either links it to an existing SIREN or creates a new company file. This is a
known friction point — left unresolved for now, to be designed once the basic inbox
flow is working.

---

## Background worker

The worker scans all company files for SIRENs where `compute_enrichment_state()`
returns at least one `pending` step, then calls `enrich_company()` for each.

Triggered via a separate CLI command (`uv run anpe enrich`) or on startup.
`failed` steps are not retried automatically — they surface for user review.

**Open design question:** a pure Python loop is brittle — it cannot handle ambiguous
results, decide whether to skip a failed step, or notice that a freeform inbox file
needs company identification. An autonomous LLM agent would handle these cases
naturally, but introduces its own risks (runaway API calls, unintended writes, quota
burn). Not designed yet — the interactive enrichment path comes first.

---

## Quota management

| Source | Cost | When to use |
|---|---|---|
| DuckDuckGo HTML | free | always, first pass |
| Direct HTTP fetch | free | after website URL identified |
| Tavily | 1000 req/month | `to_look_at` companies only, or user-triggered |

Tavily budget must not be spent during bulk discovery — only after the user has
expressed interest in a company.

---

## Open questions

- LLM summarization: summarize per step (each step writes a summary to the company `.md`) or one final summarization pass after all steps complete?
- `raw_data/` retention: keep raw HTML/JSON forever, or prune after summarization?
- General searches (news, forums) not tied to one company: same JSONL structure but stored where? Possibly `raw_data/_global/`.
