# 2026-05-03 — eval_summarize: model comparison and fixture improvements

## What was done

### Model listing script

`scripts/list_mistral_models.py` — calls `/v1/models` with the configured API key
and prints a CSV of all available models (id, name, context length, capabilities).
Source of truth pulled from `docs/references/openapi_mistral.yaml`.

### eval_summarize improvements

Two new models added to `MODELS` in `scripts/eval_summarize.py`:
- `ministral-14b-2512`
- `mistral-medium-2604`

`FIXTURES` inline list replaced by a load from `scripts/eval_fixtures/fixtures.json`.

### fixtures.json

New file `scripts/eval_fixtures/fixtures.json` replaces the inline `FIXTURES` list.
Each fixture now has a realistic `previous_summary` field that mirrors the SIREN block
produced by `siren_process` (name, SIREN, NAF, category, headcount, address).

The `aquamont` and `arkanis` fixtures are explicitly tagged `GE` / `10 000+ employees`
/ billion-euro revenue to give the model the signals it needs to fire `not_relevant`.

The `truncated_html` fixture has a non-empty previous summary to test accumulation.

## Eval results — two runs

**Run 1** (`20260503T164203.jsonl`) — empty `previous_summary` for all fixtures.

**Run 2** (`20260503T190834.jsonl`) — with SIREN context in `previous_summary`.

### Key findings

| issue | models affected |
|---|---|
| `not_relevant` never fires for GE/multinational | all four models |
| `not_relevant` false-positive on noisy input | ministral-8b, ministral-14b |
| `no_data` → targets rule violated | ministral-8b, ministral-14b |

- `mistral-small-2603` and `mistral-medium-2604` are the reliable tier: they follow
  output rules and handle noisy input correctly.
- Adding SIREN context did not fix the `not_relevant` GE failure — confirmed to be a
  system prompt gap, not a missing-context problem.
- `mistral-small` still occasionally targets bare news domains (e.g. `lemonde.fr`)
  instead of specific article URLs.

## Next

### System prompt rewrite (`anpe/prospect/summarize.py`)

Two changes identified:

1. **Role framing**: replace "enrichment assistant" with a job-search prospecting
   context — building dossiers on French PME/ETI worth approaching for a tech job.
   This gives the model a basis for relevance judgements.

2. **`not_relevant` — add case (b)**: currently only covers entity mismatch. Add
   an explicit out-of-scope trigger: GE, 10 000+ employees, multinational, public
   sector, unrelated industry. In case (b), `new_targets` must be empty (no retry).

Draft rule:
```
- status "not_relevant": use when EITHER:
    a) the fetched data clearly belongs to a different entity (disambiguation, wrong
       company). Propose a more specific DDG query in new_targets to retry.
    b) the company is out of scope: large group (GE, 10 000+ employees, multinational),
       public sector, or unrelated industry (defence, utilities, retail…).
       Leave new_targets empty — no point continuing.
```

Re-run eval after the prompt rewrite to verify Aquamont and Arkanis now return
`not_relevant`, and that Nexalia noisy no longer triggers a false positive.
