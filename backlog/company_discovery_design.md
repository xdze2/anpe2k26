# Company Discovery — Design Notes

## Goal

Let the user discover companies matching their job search criteria.
Example query: *"What companies near Bordeaux are doing AI integration for wine production?"*

---

## Data sources

### SIRENE API (`recherche-entreprises.api.gouv.fr`)

Free, no auth, 7 req/s limit. Two useful endpoints:

- **`/search`** — text search (`q=`) + filters. `q=` only matches company **name**, not activity description. Useful filters: `activite_principale` (NAF codes), `departement`, `categorie_entreprise`.
- **`/near_point`** — geographic search by lat/lon + radius (max 50km). Same NAF filters available.

**Key limitation:** SIRENE has no free-text activity description. The only way to filter by domain is via NAF codes. The agent must translate user intent → NAF codes (using the existing `naf_search` tool) before searching.

---

## Directory structure

All user-generated data lives under one root (`anpe_data/`) so it can be backed up as a single private git repo.

```
anpe_data/                  ← private git repo
  profile.md
  companies/
    <siren>_<name_slug>.md  ← one file per company, SIREN is the stable key
  logs/
    log_<DATE_ISO>.md       ← chat transcripts, for debugging and analysis
  raw_data/
    <siren>_<name_slug>/    ← future: raw web captures (HTML, PDFs...)
  cache/
    sirene_searches/        ← gitignored inside anpe_data/ (ephemeral, regenerable)
      <city>_<radius>km_<naf_hash>.json

```

`ANPE_DATA_DIR` in `.env` points to the `anpe_data/` folder (default: `./anpe_data`). This allows the user to place it outside the project directory.

---

## Company files

Each company gets one markdown file, named `<siren>_<name_slug>.md`. The SIREN is the stable key — never changes, used to link across data sources.

### Frontmatter

```yaml
---
siren: "123456789"
name: Acme Viti-Tech
naf: 62.01Z
status: to_look_at   # discarded | to_look_at | good | very_good
found_via: bordeaux_30km_6201Z_2026-04-29
date_found: 2026-04-29
---
```

Status lives in frontmatter — flat folder, no moving files. Browsable by category via `grep -rl "status: good" anpe_data/companies/`. Symlinks under `companies/by_status/` can be generated on demand if a directory view is needed.

### Body

```markdown
# Acme Viti-Tech

**Adresse:** 12 rue des Vignes, 33000 Bordeaux
**Taille:** 10-19 salariés

## Web
- Site: acme-vitilab.fr

## Notes
Agent / user notes here.

## Historique
- 2026-04-29 : découverte via SIRENE
```

---

## Search tool design

One tool: `search_companies(city, radius_km, naf_codes, page)`.

Internal flow:
1. Geocode `city` → lat/lon (reuse `geocode_city()` from `geo_api.py`)
2. Check cache: `cache/sirene_searches/<city>_<radius>km_<naf_codes>.json` with a `fetched_at` timestamp. TTL: 7 days.
3. If cache miss: call `/near_point` with lat/lon + radius + NAF codes. Save full results to cache.
4. Save discovered SIRENs to `anpe_data/companies/` (create file if not exists, never overwrite).
5. Return a paginated summary to the LLM: first N results (name, SIREN, NAF, address). Not the full 200.

The LLM never receives 200 companies at once. It gets a page of ~10, presents them, the user reacts, and can ask for more.

---

## Enrichment (next step)

Once a company is discovered via SIRENE, a separate `enrich_company(siren)` tool would:
- Fetch the company website
- Search LinkedIn / news
- Save results to `raw_data/<siren>/` and update the company markdown

This is not yet implemented. SIRENE alone cannot tell you *what a company actually does* — enrichment is what makes the search useful for "AI + wine" type queries.

---

## Open questions / future work

- `enrich_company` tool: website fetch + summarise → update company file
- Scanning flow: agent works through a list of `to_look_at` companies, presents each, asks for user rating
- Index/search across company files by frontmatter fields (status, NAF, date)
- `raw_data/` structure and retention policy
