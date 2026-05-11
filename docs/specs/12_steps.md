# Steps reference

Each step is a self-contained CLI command. It reads files from the vault, does one
thing, and writes files back. No shared runner, no engine — just a loop with a
`do_max` guard and an overwrite flag.

Common conventions:

- Skip if output already exists (unless `--overwrite`).
- Skip if required input is missing.
- `do_max` caps the number of items processed in one run.
- API results are cached locally under `cache_data/`.
- Node IDs follow the pattern `{slug}_{siren}` (e.g. `visiativ_solutions_387495799`).

- API clients are in `anpe/clients/`.
- Rate limit enforced per resource (DDG, Mistral).

---

## bootstrap

**Description:** Reads the search profile and calls the Recherche Entreprises API to
build an initial listing of candidate companies. Filters by NAF code, geographic
radius, and headcount band. Deduplicates by SIRET.

**CLI:** `anpe bootstrap`

**Args:**

- `overwrite` (bool) — re-generate even if output exists

**Inputs:**

- `USER_VAULT/seed_query.yaml` — search profile (NAF codes, locations with radius,
  headcount range)

**Outputs:**

- `USER_VAULT/listing.jsonl` — one JSON object per company

**External resources:**

- Geo API (lat/lon resolution)
- Recherche Entreprises API (search by département + NAF)

**Used methods / functions:**

- `bootstrap/pipeline.py::run()` — full pipeline (load → fetch → filter → dedup)
- `bootstrap/search.py::fetch_pair()` — fetch one (département, NAF) pair
- `bootstrap/filter.py::within_radius()`, `tranche_in_range()` — spatial and size filters
- `seed_fn.py::node_id_for()` — build node IDs downstream

**Output fields (`listing.jsonl` rows):**

```
siret, siren, nom_complet
naf_code, naf_label
adresse, code_postal, commune
lat, lon, distance_km, matched_city
tranche_effectif, categorie_entreprise, date_creation
```

---

## fetch_siren

**Description:** For each company in the listing, fetches the full company record from
the Recherche Entreprises API. Produces one JSON file per company node.

**CLI:** `anpe fetch_siren [--do-max N] [--overwrite]`

**Args:**

- `do_max` (int, default 10) — max companies to fetch
- `overwrite` (bool) — re-fetch even if output exists

**Inputs:**

- `USER_VAULT/listing.jsonl` — company list from bootstrap

**Outputs:**

- `USER_VAULT/nodes/<node_id>/fetch_siren_<node_id[:8]>.json` — raw API response

**External resources:**

- Recherche Entreprises API (lookup by SIREN)

**Used methods / functions:**

- `clients/siren.py::siren_fetch(siren)` — HTTP call, returns raw JSON string
- `seed_fn.py::node_id_for()` — derive node ID from nom_complet + siren

**Output fields:**
the raw siren record

```
siren, nom_complet, categorie_entreprise
activite_principale (NAF code), section_activite_principale
tranche_effectif_salarie
date_creation
siege: { nom_commercial, libelle_commune, commune, geo_adresse, ... }
dirigeants: [ { nom, prenom, qualite, ... } ]
```

---

## fetch_ddg

**Description:** For each company with a siren file, searches DuckDuckGo for the
company name and stores the raw search results. The search query is derived from the
commercial name and NAF section.

**CLI:** `anpe fetch_ddg [--do-max N] [--overwrite]`

**Args:**

- `do_max` (int, default 10)
- `overwrite` (bool)

**Inputs:**

- `USER_VAULT/nodes/<node_id>/fetch_siren_<...>.json` — siren data (for query construction)

**Outputs:**

- `USER_VAULT/nodes/<node_id>/fetch_ddg_<node_id[:8]>.json` — raw DDG search results

**External resources:**

- DuckDuckGo search (via `clients/ddg.py`)

**Used methods / functions:**

- `fetch_ddg_step.py::_ddg_target(siren_raw)` — derive search query (commercial name +
  `" entreprise informatique"` for NAF section J, else `" entreprise"`)
- `clients/ddg.py::ddg_search(query)` — HTTP call

**Output fields:**

```
(raw DDG response — list of search result objects with title, url, body)
```

> **TODO:** include query metadata in the output (`ts`, `query`).
> **Note:** search suffix is hard-coded per NAF section (`" entreprise informatique"` for J, `" entreprise"` otherwise).

---

## summarize_ddg

**Description:** Calls an LLM to read the raw DDG search results alongside the siren
company profile and produce a structured summary. Identifies whether the company is
relevant and extracts follow-up targets.

**CLI:** `anpe summarize_ddg [--do-max N] [--overwrite]`

**Args:**

- `do_max` (int, default 10)
- `overwrite` (bool)

**Inputs:**

- `USER_VAULT/nodes/<node_id>/fetch_ddg_<...>.json` — raw DDG results
- `USER_VAULT/nodes/<node_id>/fetch_siren_<...>.json` — siren data (company profile context)

**Outputs:**

- `USER_VAULT/nodes/<node_id>/summarize_ddg_<node_id[:8]>.json`

**External resources:**

- Mistral LLM API (via `clients/mistral.py`)

**Used methods / functions:**

- `summarize_fn.py::ddg_summarize(raw_data, previous_summary, company_profile)` — LLM call
- `summarize_ddg_step.py::_fmt_company_profile(siren_raw)` — format siren data for prompt
- NAF label lookup via `tools/naf.py::_load_csv_index()`

**Output fields:**

```
status: str                      # "ok" | "not_relevant" | "no_data"
summary: str                     # markdown narrative (< 300 words)
new_targets: list[{tool, target}]  # follow-up fetch/DDG targets suggested by the LLM
model: str                       # model name used
version: str                     # prompt version hash
prompt: str                      # full prompt sent to LLM
```

---

## llm_eval

**Description:** Scores each summarized company against the user's search profile.
Assigns a fit level and lists dealbreakers and uncertainty. Reads the user profile
from `user_preference.md`.

**CLI:** `anpe llm_eval [--overwrite] [--skip-non-relevant]`

**Args:**

- `overwrite` (bool)
- `skip_non_relevant` (bool, default True) — skip nodes where summarize status ≠ ok

**Inputs:**

- `USER_VAULT/nodes/<node_id>/summarize_ddg_<...>.json` — LLM summary
- `USER_VAULT/user_preference.md` — user search profile (dealbreakers, desired role, etc.)

**Outputs:**

- `USER_VAULT/nodes/<node_id>/llm_eval_<node_id[:8]>.json`

**External resources:**

- Mistral LLM API (`mistral-small-2603`)

**Used methods / functions:**

- `summarize_ddg_step.py::_fmt_summary_for_eval(sum_data)` — extract `summary` text from the summarize output
- `eval_fn.py::llm_eval(summary, profile)` — LLM call, returns `EvalResult`

**Output fields:**

```
score: str           # "good" | "maybe" | "discard" | "enrich"
fit: str             # one-sentence deciding factor
dealbreakers: list   # profile dealbreakers that fired
uncertainty: str     # "low" | "medium" | "high"
prompt: str          # full prompt
```

---

## review

**Description:** Interactive terminal step. Displays a formatted company card (siren
data + DDG summary + eval score) and asks the user to react. Saves the reaction to a
file. Pressing Escape or Ctrl+C stop the review.

**CLI:** `anpe review [--skip-non-relevant] [--do-max N] [--random] [--overwrite] `

**Args:**

- `do_max` (int, default 10)
- `random` pick node at random
- `skip_non_relevant` (bool, default True)
- `overwrite` (bool)

**Inputs:**

- `USER_VAULT/nodes/<node_id>/summarize_ddg_<...>.json`
- `USER_VAULT/nodes/<node_id>/fetch_siren_<...>.json`
- `USER_VAULT/nodes/<node_id>/llm_eval_<...>.json` (optional)

**Outputs:**

- `USER_VAULT/nodes/<node_id>/user_review_<node_id[:8]>.json`

**External resources:**

- User (interactive terminal input via `questionary`)

**Used methods / functions:**

- `steps/view.py::node_view(vault, summary_uri, siren_uri, eval_uri)` — render markdown card
- `questionary.select()` — arrow-key prompt
- `rich.Console` — terminal rendering

**Output fields:**

```
node_id: str
reaction: str        # "interested" | "not_interested" | "more_data"
ts: str
```

---

## list

**Description:** Prints a formatted table of all companies in the vault, optionally
filtered by state or score, sorted by a given field.

**CLI:** `anpe list [--skip-non-relevant] [--nbr N] [--sort-field FIELD] [--state STATE]`

**Args:**

- `skip_non_relevant` (bool, default True)
- `nbr` (int, optional) — max rows to show
- `sort_field` (str, optional) — field to sort by
- `state` (str, optional) — filter by review reaction or eval score

**Inputs:**

- `USER_VAULT/nodes/<node_id>/` — all available artifacts per node

**Outputs:** _(stdout only — no files written)_

**External resources:** _(none)_

**Used methods / functions:**

- `steps/view.py` — read and format per-node data
- `rich` — table rendering

**Output fields:** N/A (terminal display only)

---

## view

**Description:** Prints a formatted markdown summary for a single company node,
combining siren data, DDG summary, and eval score.

**CLI:** `anpe view <node_id>`

**Args:**

- `node_id` (str, required) — the node identifier

**Inputs:**

- `USER_VAULT/nodes/<node_id>/` — all available artifacts for that node

**Outputs:** _(stdout only — no files written)_

**External resources:** _(none)_

**Used methods / functions:**

- `steps/view.py::node_view(vault, summary_uri, siren_uri, eval_uri)` — render markdown

**Output fields:** N/A (terminal display only)
