# 2026-05-01 — Model choice & eval setup for llm_summarize

## What changed

### Eval infrastructure

Built a model comparison eval for `llm_summarize`:

- `scripts/eval_summarize.py` — runs all model × fixture combinations, prints compact
  per-call summary to stdout, writes results to `scripts/eval_results/<timestamp>.jsonl`.
  Results are flushed after each call (not at the end) so partial runs are never lost.
  A `CALL_DELAY_S = 3.0` constant adds a logged pause between calls to stay within
  per-minute rate limits.

- `scripts/eval_fixtures/` — 6 fixture files (anonymised, see below):
  - `ddg_nexalia_noisy.txt` — real company buried in DDG noise (associations, events)
  - `ddg_vectorix_clean.txt` — clean DDG results, obvious website URLs present
  - `ddg_aquamont_irrelevant.txt` — large multinational, should be `not_relevant`
  - `ddg_arkanis_irrelevant.txt` — large defense group + philosopher disambiguation noise
  - `ddg_empty.txt` — empty string (DDG returned nothing)
  - `fetch_truncated_html.txt` — mid-sentence cut HTML page (anticipates `fetch` tool)

  All fixtures are anonymised: real company names replaced with fictional ones
  (Nexalia, Vectorix, Aquamont, Arkanis) to avoid committing real company data.
  The real raw data files remain in `user_data/nodes/` (gitignored).

### Models under evaluation

Three candidates, all free on OpenRouter:

| model | params (active) | notes |
|---|---|---|
| `google/gemma-4-26b-a4b-it:free` | 26B MoE (3.8B active) | fast, native function calling |
| `google/gemma-4-31b-it:free` | 31B dense | strong instruction following |
| `nvidia/nemotron-3-super-120b-a12b:free` | 120B MoE (12B active) | strongest, slowest |

`openai/gpt-4o-mini` dropped — no credits on the account.

### Prompt fixes in `anpe/enrich/summarize.py`

Two fixes applied based on eval results:

1. Added rule: `If status is "no_data", new_targets must be empty.`
   Nemotron returned `no_data` correctly on empty input but hallucinated a generic DDG
   query as a follow-up target.

2. Error handling for API failures:
   - HTTP 402 (no credits) → raises `LLMCreditsError` immediately, no retry
   - HTTP 429 (rate limited) → retries up to `MAX_RETRIES = 3` with exponential backoff
     starting at 5s (5 → 10 → 20s), with a log line on each retry
   - Other errors → re-raised immediately

### Spec file

`docs/specs/61_model_choice_for_summarization.md` — captures task profile, fixture
table, candidate models, and results so far.

## Eval results (partial — 2026-05-01)

OpenRouter free tier: 50 req/day. Hit ~25 requests during session.

**Both Gemma models blocked** — upstream Google AI Studio rate limit (429) throughout
all test runs. Separate from OpenRouter's daily quota; requires adding a personal
Google AI Studio key to OpenRouter to bypass.

**Nemotron results:**

| fixture | status | targets | notes |
|---|---|---|---|
| `nexalia_noisy` | `ok` | 0 | Good summary, but missed website URL in data |
| `aquamont_irrelevant` | `not_relevant` | 0 | Correct |
| `arkanis_irrelevant` | `not_relevant` | 0 | Correct |
| `empty_input` | `no_data` | 1 | Correct status, hallucinated target → prompt fix applied |

`vectorix_clean` and `truncated_html` not reached (quota/rate limit).

**Key finding:** `new_targets` extraction is the real problem — the company website URL
`nexalia-developpement.fr` was present in the DDG data but Nemotron produced 0 targets.
This is a prompt tuning problem, not a model capability gap.

## Open questions / next session

- **Prompt tuning for `new_targets`**: the loop stops after one step because the LLM
  rarely proposes follow-up targets. The fetch cache allows re-running without re-fetching.
  See `docs/specs/31_poc_enrich_pipeline.md` § "Next session — prompt tuning" for the plan.

- **Full model comparison**: run the complete eval once daily quota resets (tomorrow).
  Gemma models need Google AI Studio key or wait for upstream rate limit to clear.

- **What the LLM actually receives**: pydantic-ai implements structured output via tool
  calling (`final_result` tool), not JSON schema injection into the system prompt.
  Exact schema sent to the model not yet inspected — interrupted mid-investigation.
  Worth knowing for prompt tuning: the model sees a tool definition, not a schema block.
