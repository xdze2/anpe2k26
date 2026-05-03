# 2026-05-03 — Bootstrap spec: generate company listing from SIRENE API

## Context

The enrichment pipeline has no automated way to produce its input list of companies.
Up to now the list was curated by hand. This session designed the upstream step that
generates it automatically from job-search criteria.

## What was decided

### Command: `anpe bootstrap run`

Reads `user_profile.yaml` (project root), writes `user_data/company_listing.csv`.
No path options. Idempotent — safe to re-run.

### `user_profile.yaml`

Hand-written. Contains:
- `naf_codes` — list of NAF codes of interest
- `locations` — list of cities, each with `lat`, `lon`, `radius_km`, and `departements`
- `size` — `tranche_min` / `tranche_max` using SIRENE tranche codes
- `etat_administratif` — default `"A"` (active only)

### Two-stage geographic filter

API query uses `departement` (coarse, avoids needing commune lists).
Post-query distance filter uses `lat`/`lon`/`radius_km` from the profile (precise).
Rationale: the API doesn't support radius natively on `/search`; `/near_point` exists
but lacks the size/NAF filter combination needed. Bulk-then-filter is simpler and
the cache absorbs the extra API calls.

### Cache layer

One JSON file per `(departement, naf_code)` pair under `user_data/bootstrap_cache/`.
Write-once — re-running reuses cached pages. `--refresh` flag invalidates all.
Granularity means adding a new NAF code only fetches what's missing.

### SIREN vs. SIRET

The API returns unités légales (SIREN). Each result contains `matching_etablissements`
(SIRETs that matched the search filters) and `siege` (HQ).

Output rows are per **établissement** (SIRET) — the physical locations in the target
geography — with `siren` attached for later enrichment lookups. Extraction rule:
use `matching_etablissements` if non-empty, fall back to `siege`.
`limite_matching_etablissements` set to 100 (API max) to avoid missing local offices
of multi-site companies.

### Size filter: company-level tranche

`tranche_effectif_salarie` on the top-level result (company-wide) is used, not the
établissement-level tranche. A small local branch of a 200-person company is still a
200-person company and worth including.

### Output columns

```
siret, siren, nom_complet, naf_code, naf_label,
adresse, code_postal, commune,
lat, lon, distance_km, matched_city,
tranche_effectif, categorie_entreprise, date_creation
```

`siren` flows into the enrichment pipeline. `siret` + `adresse` identifies the office.

## Spec

Full design written to `docs/specs/32_bootstrap_using_siren.md`.

## Next

- Implement `anpe bootstrap run`: load profile → query API with cache → extract
  établissements → distance filter → deduplicate by SIRET → write CSV
- Wire `company_listing.csv` as input to the enrichment pipeline (replacing manual seeds)
