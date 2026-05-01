---
status: draft
---

# Model choice for `llm_summarize`

## Task profile

`llm_summarize` receives raw fetched text (DDG results, HTML pages, …) and a previous
summary, and must return a structured `EnrichResult`: status, markdown summary, and a
list of follow-up fetch targets. The key capabilities required are:

- **Information extraction** — find URLs, company names, and relevant facts in noisy text
- **Instruction following** — respect output rules (status values, target constraints)
- **Structured output** — produce valid JSON reliably
- **French content** — DDG results and web pages are often in French

Latency matters (interactive enrichment loop). Cost matters (high call volume expected).
Context window needed is moderate — a few thousand tokens per call.

## Eval setup

Script: `scripts/eval_summarize.py`
Fixtures: `scripts/eval_fixtures/` — 6 cases:

| id | type | expected |
|---|---|---|
| `nexalia_noisy` | DDG — real company buried in association noise | `ok`, 1-2 targets |
| `vectorix_clean` | DDG — clean results with obvious URLs | `ok`, 1-2 targets |
| `aquamont_irrelevant` | DDG — large multinational | `not_relevant` |
| `arkanis_irrelevant` | DDG — large defense group + philosopher noise | `not_relevant` |
| `empty_input` | empty string | `no_data`, no hallucinated targets |
| `truncated_html` | mid-sentence cut HTML page | `ok` with partial info, or `no_data` |

Results saved to `scripts/eval_results/<timestamp>.jsonl`.

## Candidates

| model | params (active) | context | notes |
|---|---|---|---|
| `google/gemma-4-26b-a4b-it:free` | 26B MoE (3.8B active) | 256K | fast, native function calling |
| `google/gemma-4-31b-it:free` | 31B dense | 256K | strong instruction following, multilingual |
| `nvidia/nemotron-3-super-120b-a12b:free` | 120B MoE (12B active) | 1M | strongest reasoning, slower |

## Results so far (2026-05-01)

Only `nemotron-3-super` produced results — both Gemma models were blocked by upstream
Google AI Studio rate limits (429) throughout testing. OpenRouter free tier: 50 req/day.

**Nemotron on `nexalia_noisy`:** status `ok`, good summary, but **0 new_targets** despite
the company website URL being present in the DDG data. Confirmed: target extraction is
the prompt tuning target, not a model capability gap.

**Nemotron on `aquamont_irrelevant` and `arkanis_irrelevant`:** `not_relevant` correctly,
concise summaries, 0 targets. Relevance filtering works well.

**Nemotron on `empty_input`:** `no_data` correctly, but hallucinated a generic DDG query
as a target. Fixed in prompt: *"If status is `no_data`, new_targets must be empty."*

## Open questions

- Can Gemma models be tested once Google AI Studio rate limits reset?
- Does the smaller Gemma 26B A4B match Nemotron quality on this task?
- Is structured output (JSON) reliable across all three models?

## Decision

Pending full eval. **Nemotron is the working baseline.** Switch if Gemma 26B A4B matches
quality with lower latency.
