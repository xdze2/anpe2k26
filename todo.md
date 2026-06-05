# MVP Web UI — todo

Reference files:
- [anpe/web.py](anpe/web.py) — Flask app (all routes, HTML generation, data loading)
- [anpe/engine/vault.py](anpe/engine/vault.py) — Vault path resolution
- [user_vault/listing.jsonl](user_vault/listing.jsonl) — bootstrap output, one JSON per company; has `matched_city`, `naf_code`, `siren`
- [user_vault/nodes/](user_vault/nodes/) — one dir per node; contains `fetch_siren_*.json`, `fetch_ddg_*.json`, `summarize_ddg_*.json`, `eval_*.json`, `review_*.json`
- [user_vault/seed_query.yaml](user_vault/seed_query.yaml) — search config (NAF codes, locations, size range)
- [docs/specs/12_steps.md](docs/specs/12_steps.md) — step reference (file formats, field names)

Node data fields available:
- `summarize_ddg_*.json`: `status`, `summary` (markdown, first line = "Type: · Domaine: · Marché:"), `new_targets`
- `eval_*.json`: `score` (good/maybe/discard/enrich), `fit`, `dealbreakers`, `uncertainty`, `profile_uri`
- `fetch_siren_*.json`: `siren`, `nom_complet`, `activite_principale` (NAF), `tranche_effectif_salarie`, `categorie_entreprise`, `siege.nom_commercial`, `siege.libelle_commune`
- `review_*.json` (written by CLI or web): `node_id`, `reaction` (interested/not_interested/more_data), `comment`, `ts`
- `listing.jsonl` (join by `siren`): `matched_city`, `naf_code`, `naf_label`

---

## Table view

- [x] **Add columns: City, NAF, Domaine**
  - City and NAF already loaded in `_load_rows()` ([web.py:98](anpe/web.py#L98)) but not rendered in the table ([web.py:145-158](anpe/web.py#L145))
  - Domaine: parse summary first line — strip `**Type:** ... · **Domaine:** X · ...` to extract the Domaine value
  - Add these three columns to the `<thead>` and each `<tr>`

- [x] **Add matched_city (search batch) column**
  - Load `listing.jsonl`, build a `siren → matched_city` dict
  - Join it in `_load_rows()` ([web.py:31](anpe/web.py#L31)) using the `siren` field already in `siren_data`
  - Add as a column in the table — useful for isolating nodes from a new search

- [x] **Add filter bar**
  - Dropdowns for: `score`, `reaction`, `matched_city`, `categorie_entreprise`
  - Text search on company name
  - Client-side JS only (no round-trip) — hide/show `<tr>` rows

- [x] **Sortable column headers**
  - Click a `<th>` to sort asc/desc by that column
  - Client-side JS; keep default sort = score then node_id

- [x] **Add Catégorie column** (PME/ETI/GE) with filter dropdown

---

## Node detail

- [ ] **Raw DDG link**
  - Add route `GET /raw/<node_id>/ddg` returning `fetch_ddg_*.json` as JSON
  - Link it from the detail page ([web.py:186](anpe/web.py#L186)) near the summary section

- [ ] **Profile link**
  - `profile_uri` is already in `eval_*.json` — read it and display filename + a link
  - Add route `GET /profile` (or `/profile/<filename>`) that serves the markdown file as `<pre>` or rendered HTML

---

## Review form

- [ ] **POST endpoint**
  - Route: `POST /node/<node_id>/review`
  - Writes `user_vault/nodes/<node_id>/review_<node_id[:8]>.json`
  - Fields: `node_id`, `reaction` (interested/not_interested/more_data), `comment` (optional), `ts` (ISO UTC)
  - Same format as CLI review step (see [docs/specs/12_steps.md](docs/specs/12_steps.md) review section)

- [ ] **Review UI in node detail**
  - Three buttons: Interested / Not interested / More data
  - Optional comment `<textarea>`
  - `<form method="POST" target="_self">` inside the iframe so it reloads only the detail panel
  - Show current reaction at top if `review_*.json` already exists

- [ ] **Table reaction refresh after review**
  - After submitting, the iframe reloads the detail page — but the table row reaction cell stays stale
  - Option A: reload the full parent page on form submit (simple, loses selection)
  - Option B: use `window.parent.postMessage` from iframe after submit to update just that cell (cleaner)
  - Decide and implement
