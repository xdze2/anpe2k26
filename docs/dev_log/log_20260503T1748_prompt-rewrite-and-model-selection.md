# 2026-05-03 — prompt rewrite, model selection, cost estimate

## What was done

### System prompt rewrite (`anpe/prospect/summarize.py`)

Three improvements to `_SYSTEM`:

1. **Role framing**: changed from "enrichment assistant" to "job-search prospecting
   assistant building intelligence dossiers on French PME/ETI". Gives the model a
   basis for relevance judgements.

2. **SIREN as ground truth**: the Company profile block is now explicitly described
   as authoritative registry data. The model is told to trust it for size/category
   decisions, not the web content.

3. **`not_relevant` — two-case rule**:
   - Case (a): entity mismatch (wrong company, disambiguation) → propose retry DDG
     query in `new_targets`.
   - Case (b): out of scope (GE, 10 000+ employees, multinational, public sector,
     unrelated industry) → `new_targets` must be empty. Explicit trigger: if
     Company profile shows `Category: GE` or `Headcount: 10 000+`, always use (b).

4. **`no_data` rule hardened**: "new_targets MUST be empty — do NOT suggest DDG
   queries or URLs to compensate." Targets the observed failure mode where medium
   and 14b proposed search queries despite returning `no_data`.

5. **Summary scope**: told not to repeat information already in the Company profile
   block.

### Company profile as a separate prompt section

`llm_summarize()` gains a `company_profile: str = ""` parameter, injected as
`## Company profile` before `## Previous summary`. SIREN data is no longer mixed
into the previous summary — it's stable ground truth the model can't accidentally
overwrite or paraphrase away.

Signature:
```python
async def llm_summarize(
    raw_data: str,
    previous_summary: str,
    company_profile: str = "",
    prompt_file: Path | None = None,
) -> EnrichResult:
```

Production call site (`pipeline.py`) passes `company_profile=""` implicitly — no
regression. Wiring `NodeDir.get_company_profile()` is deferred.

### eval fixtures updated

`scripts/eval_fixtures/fixtures.json`: SIREN data moved from `previous_summary`
to a new `company_profile` key. Fields trimmed to what the model actually uses:
Name, SIREN, NAF (text only, no code), Category, Headcount, City. Dropped:
Address, Created date, Status, Revenue.

`truncated_html` fixture: `previous_summary` now contains only the earned
web-sourced sentence; the SIREN block moved to `company_profile`.

### Model switch

`summarize.py` switched from `OpenAIChatModel` + `OpenAIProvider` (OpenAI-compat
shim) to `MistralModel` + `MistralProvider` (native pydantic-ai integration),
matching the eval script. Model hardcoded to `mistral-small-2603`.

### Eval run (`20260503T192902.jsonl`) — results with new prompt

| fixture | 8b | small | 14b | medium |
|---|---|---|---|---|
| nexalia_noisy | not_relevant ❌ | ok ✅ | not_relevant ❌ | ok ✅ |
| vectorix_clean | ok ✅ | ok ✅ | ok ✅ | ok ✅ |
| aquamont_irrelevant | not_relevant ✅ | not_relevant ✅ | not_relevant ✅ | not_relevant ✅ |
| arkanis_irrelevant | not_relevant ✅ | not_relevant ✅ | not_relevant ✅ | not_relevant ✅ |
| empty_input | no_data ✅ | no_data ✅ | no_data+targets ⚠️ | no_data+targets ⚠️ |
| truncated_html | ok ✅ | ok ✅ | ok ✅ | ok ✅ |

GE / `not_relevant` is now fully fixed across all models — the main failure from
run 2. `mistral-small-2603` is the only model that passes all rule compliance
tests cleanly.

### Model selected: `mistral-small-2603`

- Only model with clean rule compliance on all fixtures.
- `ministral-8b` and `ministral-14b`: false-positive `not_relevant` on noisy input
  (nexalia_noisy).
- `mistral-medium-2604`: `no_data` rule violation (proposes targets despite empty
  input); also 10–20× slower on some fixtures (21s vs 3s on vectorix_clean).

### Cost estimate

At ~1,150 input tokens and ~175 output tokens per call, with `mistral-small-2603`
pricing ($0.15/M in, $0.60/M out):

- 1,000 calls ≈ $0.28 total.
- Even 10× larger inputs (full page fetches) → ~$3/1,000 calls.

## Next

- Wire `company_profile` into the production pipeline: `NodeDir` needs a
  `get_company_profile()` method that formats the SIREN fields in the same trimmed
  style as the fixtures.
- Re-run eval after the `no_data` prompt hardening to verify medium and 14b now
  comply (not a blocker for production, since small is selected).
- `anpe prospect list` — overview of all nodes.
