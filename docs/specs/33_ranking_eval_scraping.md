---
status: draft
---

# Ranking, eval, and web scraping

This document covers three interconnected features that close the feedback loop
between the enrichment pipeline and the user:

1. **Terminal review** — user reacts to summaries in free text
2. **Profile update** — LLM synthesizes reactions into an updated search profile
3. **Node scoring** — LLM scores each node against the profile
4. **Web fetch** — richer summaries via direct page scraping

These build on top of the existing `siren → ddg → llm_summarize` pipeline.

---

## 1. Terminal review (`anpe prospect review`)

Already implemented. Documented here for completeness and as input to the
profile update design.

### Storage: `reviews.jsonl`

Append-only log per node, same pattern as `fetch.jsonl`.

```jsonl
{"ts": "...", "reaction": "exactement ce que je cherche, NewSpace petit"}
{"ts": "...", "skip": true}
{"ts": "...", "reaction": "trop ESN, pas de produit propre"}
```

A node is considered reviewed when its latest event has a non-empty `reaction`.
Skipped nodes reappear in the next review session.

### Design constraints

The user and the LLM share exactly the same information: the summary body.
No browser, no external context. This is intentional — it keeps the feedback
loop grounded. Reactions are only as good as the summary, which puts the
weight on summary quality (see section 4).

---

## 2. Profile update

### Trigger

Manual: `anpe profile update`. Possibly also auto-triggered after N new
reactions (TBD).

### Call shape

Single LLM call with all unincorporated reactions since the last profile
update:

```
system:
  You are updating a job-search profile based on the user's reactions to
  company summaries. Be conservative — only update what the reactions clearly
  support. Return the full updated profile text.

user:
  Current profile:
  <profile.md content>

  Recent reactions:
  - [INFINITE ORBITS] NewSpace, 20p, Toulouse — "exactement ce que je cherche"
  - [ALTECA] ESN, 500p — "trop grande, trop ESN"
  - [CHAPSVISION] cybersec, ETI — "pas mon truc"
  - [BIGBLUE] logistics SaaS, 50p — "intéressant, bon domaine"
  - [INCOMM] ESN web, 50p — "non, encore une ESN"

  Update the profile to reflect what these reactions reveal.
```

Output: full updated `profile.md` text. The user can diff and edit before
saving.

### Tracking incorporated reactions

`profile.md` frontmatter stores the last update timestamp:

```yaml
---
updated_ts: 2026-05-04T10:00:00Z
---
```

`profile update` filters reactions newer than `updated_ts`. Reactions older
than or equal to `updated_ts` are already incorporated and skipped.

### Context size

A summary + reaction pair is ~200-300 words. At 128k context (Mistral Small),
400-600 pairs fit comfortably. Not a constraint at current scale.

### Batch synthesis advantage

The LLM sees the full picture at once and can notice cross-reaction patterns
that incremental updates miss: "user said 'trop grande' on 4 different ETIs,
and reacted positively to all companies under 30 people". This is more reliable
than per-reaction delta extraction.

---

## 3. Node scoring

### Trigger

After each profile update, run scoring on all nodes with `summarize_done` and
a stale or missing score.

### Call shape

One LLM call per node (cheap, classification only):

```
system:
  Score this company against the user's search profile.
  Return one of: good | maybe | discard | enrich
  And a one-line reason.

user:
  Profile:
  <profile.md>

  Company summary:
  <summary body>
```

### Output values

| Value | Meaning | Action |
|---|---|---|
| `good` | clear match | surface to user |
| `maybe` | matches profile but something is off | surface to user with reason |
| `discard` | clear non-match | stop pipeline, mark node |
| `enrich` | not enough info to decide | re-queue fetch steps |

`maybe` always carries a one-line reason ("taille limite, ~80 personnes").
This reason is the most valuable output — it tells the user exactly what to
look at.

`enrich` feeds back into the pipeline. It should only fire when a specific
gap is identified ("no info on company size"), not as a default fallback.

### Storage

Score stored in node frontmatter:

```yaml
score: good
score_reason: "produit propre, petite équipe, domaine IA"
score_ts: 2026-05-04T10:00:00Z
score_profile_ts: 2026-05-04T10:00:00Z  # profile version used
```

`score_profile_ts` enables staleness detection: if `profile.md` `updated_ts`
is newer than `score_profile_ts`, the score is stale and needs recomputing.

### Staleness model

Two independent validity dimensions on each node:

```
summary_status:  fresh | stale | pending_fetch
score_status:    fresh | stale | missing
```

Profile update → all `score_status` set to `stale`.
New fetch + summarize → `summary_status` set to `fresh`, `score_status` set
to `stale` (summary changed, score needs recomputing).

---

## 4. Web fetch tool

### Motivation

DDG snippets give enough signal to filter obvious mismatches but are too thin
for confident scoring. The about page, careers page, or a press article gives
the LLM the cultural context, tech stack, and actual product description that
makes a summary useful.

The LLM already proposes website URLs in `new_targets` — they are currently
dropped because the `fetch` tool is not implemented.

### Implementation: `trafilatura`

```python
import trafilatura

def fetch_url(url: str) -> str:
    html = trafilatura.fetch_url(url)
    if html is None:
        raise FetchNotFoundError(url)
    text = trafilatura.extract(html, include_links=False)
    if not text:
        raise FetchNotFoundError(url)
    return text[:20_000]  # cap to avoid oversized context
```

`trafilatura` handles fetch + main-content extraction in one call. Output is
clean prose — no nav, footer, or ads. Directly usable as LLM input.

### Expected results by target type

| Target | Expected outcome |
|---|---|
| Company about page (simple) | good — product description, values, team |
| Welcome to the Jungle profile | good — culture, stack, open roles |
| Wikipedia | good — history, funding, acquisitions |
| LinkedIn company page | blocked |
| JS-heavy SPA | empty body → `not_found` |
| Cloudflare-protected | blocked |

### Manual fallback: Firefox extension

For JS-heavy or Cloudflare-protected sites, a Firefox extension + local Flask
backend captures the rendered DOM from the browser and delivers it to the
pipeline. The user browses normally; the extension fires on demand.

Wire-in: the Flask endpoint receives `(url, html_content)`, identifies the
target node by matching `url` against `new_targets` across all nodes, saves
the content as a raw file in `node/raw_data/`, and appends a `fetch_done`
event to `fetch.jsonl`. The pipeline then picks it up as a normal fetch and
runs `llm_summarize`.

URL → node matching: scan all nodes for a `put` event with a `fetch` target
whose URL matches (exact or domain-level). Ambiguous matches prompt the user
to confirm.

This fallback is the complement to `trafilatura`, not a replacement. Most
nodes won't need it.

---

## 5. Summary quality

All of the above degrades silently if summaries are thin or noisy. Current
problems observed in the wild:

**Redundant data** (already in frontmatter, should not appear in body):
- NAF code and label
- City, headcount, category
- Company name as H1 title

**LLM filler** (zero signal, should be banned by prompt):
- "Key insights for tech professionals:"
- "Key takeaway:", "Potential fit for..."
- "making it a compelling target for..."

**Missing structured fields** — the body should open with a compact header:

```
Type: éditeur · domaine: spatial, IA · marché: B2B
```

| Dimension | Example values |
|---|---|
| Type | éditeur / ESN / conseil / produit+services |
| Domaine | spatial, IA, RH, mobilité, cybersécurité, énergie... |
| Marché | B2B, B2C, B2G, mixte |

The rest of the body only contains web-sourced intelligence not inferable from
the header + frontmatter. If there is nothing new to say, the output is
`no_data`, not a paraphrase of the registry data.

This prompt rewrite is a prerequisite for reliable scoring — a bad summary
produces a bad score.

---

## Implementation order

1. **Prompt rewrite** — fix summary quality first; everything downstream
   depends on it. Add eval fixture for the thin-DDG case.
2. **`fetch` tool** (`trafilatura`) — run on nodes that already have website
   URLs in `new_targets`; validate summary improvement.
3. **Node scoring** — `score(summary, profile) → good/maybe/discard/enrich`.
4. **Profile update** — batch reaction synthesis; wire `anpe profile update`.
5. **Firefox extension integration** — manual fallback for blocked sites;
   lower priority, only needed once fetch coverage is validated.
