---
status: draft
---

# Bootstrap — generate company listing from SIRENE API

Build a company listing from search criteria rather than by hand. This is the upstream
step that produces the seed list fed into the enrichment pipeline.

## Problem

The enrichment pipeline currently operates on a manually curated list of companies.
That list needs to exist before enrichment can start. The goal here is to generate it
automatically from job-search criteria: target sectors (NAF codes), geographic zones,
and company size.

## Command

```bash
anpe bootstrap run
```

No path options. Reads `user_profile.yaml` from the project root, writes output to
`user_data/company_listing.csv`. Running it again is safe — the API cache is reused,
only the distance filtering and CSV writing are repeated.

## `user_profile.yaml`

Hand-written by the user. Example:

```yaml
naf_codes:
  - "62.01Z"   # Programmation informatique
  - "62.02A"   # Conseil en systèmes et logiciels informatiques
  - "62.02B"
  - "72.19Z"   # R&D en sciences physiques et naturelles

locations:
  - city: "Toulouse"
    lat: 43.60
    lon: 1.44
    radius_km: 30
    departements: ["31"]

  - city: "Lyon"
    lat: 45.75
    lon: 4.83
    radius_km: 20
    departements: ["69"]

size:
  tranche_min: "11"   # 10-19 employees
  tranche_max: "41"   # 500-999 employees

etat_administratif: "A"   # active companies only
```

`departements` drives the API query (coarse geographic filter).
`lat`, `lon`, and `radius_km` drive the post-query distance filter (precise).
The user fills `departements` manually — department codes are common knowledge.
`lat`/`lon` can optionally be auto-resolved from `city` via `geo_api.py`, but the user
can also fill them directly.

## Pipeline

```
1. Load user_profile.yaml
2. For each (departement, naf_code) pair:
     if not cached → paginate /search API → save raw pages to cache
3. Load all cached files → extract etablissements
4. Filter by distance from each location's lat/lon
5. Filter by company-level tranche_effectif_salarie range
6. Deduplicate by SIRET
7. Write user_data/company_listing.csv
```

### Step 2 — API queries and cache

The recherche-entreprises API (`/search`) accepts filter-only queries with no `q`
parameter. Each call uses:

- `departement` = one department code
- `activite_principale` = one NAF code
- `etat_administratif` = "A"
- `per_page` = 25 (API max)
- `limite_matching_etablissements` = 100 (API max)

One cache file per `(departement, naf_code)` pair:

```
user_data/bootstrap_cache/
  dep31_naf6201Z.json
  dep31_naf6202A.json
  dep69_naf6201Z.json
  ...
```

Each file contains the full list of raw result objects (all pages concatenated). The
cache is write-once: if the file exists, the API is not called. Add `--refresh` to
invalidate all cache files and re-fetch.

Rate limit is 7 req/s. A small delay between paginated requests is sufficient.

The API caps results at ~1000 per query. For very broad filter combinations this
silently truncates. The per-pair granularity limits exposure — a single (dep, naf)
pair rarely exceeds 1000 results. If `total_results` equals 1000 and `total_pages`
is maxed out, a warning is logged.

### Step 3 — extracting etablissements

The API returns **unités légales** (companies, SIREN) as top-level results. Each
result contains:

- `matching_etablissements` — establishments that matched the search filters
- `siege` — the registered headquarters

For the listing we want individual **établissements** (SIRET) — the physical locations
that are actually in the target geography. The extraction rule:

- Use `matching_etablissements` if non-empty
- Fall back to `siege` if `matching_etablissements` is empty

This matters because a company like Capgemini may have offices in 10 cities. We only
want the Toulouse one, not the Paris headquarters.

### Step 4 — distance filter

Each extracted établissement has a `latitude`/`longitude` on its siege/etablissement
object. Apply the haversine formula (already in `geo_api.py`) to keep only
établissements within `radius_km` of the location's `lat`/`lon`. Add `distance_km`
and `matched_city` columns to the output row.

### Step 5 — size filter

`tranche_effectif_salarie` on the **top-level result** (company-wide headcount) is
used for filtering, not the établissement-level tranche. Rationale: a small local
branch of a 200-person company is still a 200-person company and worth knowing about.
Tranche codes are ordered strings (`"11"` < `"12"` < `"21"` …), so a string
lexicographic comparison works for range filtering.

### Step 6 — deduplication

The same établissement can appear in multiple cache files (same SIRET matched by
two different NAF codes, or the company's sede matched a different dep query). Deduplicate
by SIRET — keep the first occurrence.

## Output: `user_data/company_listing.csv`

```
siret, siren, nom_complet, naf_code, naf_label,
adresse, code_postal, commune,
lat, lon, distance_km, matched_city,
tranche_effectif, categorie_entreprise, date_creation
```

`siren` is the identifier that flows into the enrichment pipeline.
`siret` + `adresse` identifies the specific office.

This file replaces the manually curated `seeds.csv` as the input to `anpe enrich`.

## What is not handled here

- Interactive editing of `user_profile.yaml` — future `anpe bootstrap edit` subcommand
- Automatic resolution of `departements` from `city` + `radius_km` — the geo_api.py
  tooling exists for this but the user fills `departements` manually for now
- Filtering on `nature_juridique` (legal form) — can be added to `user_profile.yaml`
  and passed directly as an API parameter if needed
- Enrichment scheduling from the listing — `anpe bootstrap run` stops at the CSV;
  triggering enrichment for each row is a separate step
