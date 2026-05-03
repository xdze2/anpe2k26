---
status: draft
---

### Source catalogue

The pipeline MUST support the following steps in order:

| Step            | Source           | Constraint                                  |
| --------------- | ---------------- | ------------------------------------------- |
| `sirene_fetch`  | SIRENE API       | always first                                |
| `sirene_eval`   | LLM (eval model) | base context for all subsequent evals       |
| `ddg_search`    | DDG HTML scrape  | free; first-pass for small French companies |
| `ddg_eval`      | LLM (eval model) | extracts candidate URL                      |
| `website_fetch` | direct HTTP      | fails on JS-heavy / Cloudflare sites        |
| `website_eval`  | LLM (eval model) | activity summary + match verdict            |
| `tavily_search` | Tavily API       | quota-gated; see constraints                |
| `tavily_eval`   | LLM (eval model) | updated summary + verdict                   |

## Sirene source

### Discovery

- The system MUST query SIRENE by city, radius, and NAF codes and return a paginated
  list of candidate companies.
- The system MUST geocode a city name to lat/lon before calling SIRENE.
- The system MUST cache SIRENE search results on disk (no TTL — data is stable).
- The system MUST NOT call SIRENE with a radius greater than 50 km.
- The agent MUST propose NAF codes to the user and wait for confirmation before
  calling SIRENE.
- After returning search results, the agent MUST state that the filter is by sector
  code, not by actual company activity.
- Each page of results MUST contain approximately 10 companies. Page number is an
  explicit tool argument — the agent tracks it in context.

- SIRENE `/near_point` MUST NOT be called with `radius_km > 50` (API hard limit).

### Company data

- Each company MUST have exactly one file: `companies/<siren>_<name_slug>.md`.
- The SIREN is the only stable key. The slug is decorative and never parsed.
- A company file MUST NOT be overwritten when a SIRENE search revisits a known SIREN.
- Each company file MUST include a YAML frontmatter block with: `siren`, `name`, `naf`,
  `status`, `enrichment_status`, `found_via`, `date_found`.
- `status` MUST be one of: `to_look_at`, `discarded`, `good`, `very_good`.
- `enrichment_status` MUST be one of: `in_progress`, `done`, `discarded`.
- `done` MUST be soft: enrichment can resume at any time if the user requests it.
- The `## Notes` section of a company file MUST never be overwritten by the pipeline.

## Tavily source

## Constraints

- Tavily MUST NOT be called during bulk discovery — only after the user has expressed
  interest in a specific company (`status: to_look_at` or better).
- Tavily quota: 1000 requests/month. The system SHOULD track usage or surface a
  warning before each call.
