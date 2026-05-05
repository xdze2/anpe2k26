# Roadmap and performance analysis — 2026-05-05

## What was done

Added `docs/specs/70_classifier_performance.md` — a roadmap (not a spec) for
understanding whether the pipeline actually works as a classifier. Framed around
three questions:

1. **Does the LLM eval agree with user judgments?** → confusion matrix of eval
   scores vs. hand-labeled reactions.
2. **Which profile criteria are actually driving decisions?** → coverage analysis
   of `fit` / `dealbreakers` fields across eval results.
3. **What information is structurally missing from summaries?** → enrichment
   coverage per field (headcount, tech stack, domain clarity, job offers).

Also: `prospect list` now shows the latest eval score and fit snippet per node,
with a `~` glyph to mark it as an LLM prediction.

---

## Open work — prioritized

### High priority

**`anpe prospect show <node_id>`**
There is no way to read a full summary or eval result without opening files.
Now that eval scores appear in `prospect list`, the natural next action is to
drill in. Also a prerequisite for the `summary.md` cleanup below.

**Hand-label the 40 user reactions**
Ground truth for the confusion matrix. ~40 rows, free text → yes/no/unsure.
Should be done before any profile tuning, otherwise improvements are guesswork.
Store in `user_data/ground_truth.json` or similar.

**Fix `update_profile` to write timestamped snapshots**
Currently overwrites `profile.md` in place, contradicting the immutable-record
convention. The eval pipeline already stores `profile_file` by path — if the
file is overwritten, those stored references silently become stale.
Flagged WIP in `14_pipeline_overview.md`.

### Medium priority

**Eliminate `summary.md` as a persistent file**
`summary.md` is treated as both a view and a record. The authoritative data is
in `sum_*.json`; `summary.md` is a redundant copy that can drift.
Replace with on-demand rendering in `prospect show`. See the design note in
`log_20260505T1700_spec-cleanup.md` for the full argument.
Depends on: `prospect show` existing first.

**Confusion matrix script**
Once reactions are labeled, a short script that joins `eval_results/` with
ground truth and prints the matrix. Not a CLI command — a one-off analysis
script in `scripts/`.

**Profile coverage analysis**
Scan all `eval_results/` and tally which profile criteria appear in `fit` /
`dealbreakers`. Requires fuzzy matching or manual inspection first — the LLM
paraphrases rather than quoting criteria verbatim.

### Lower priority / enrich pipeline

**`fetch_url` tool not implemented**
`31_enrich_pipeline.md` is marked active; `fetch_url` is listed as a TODO.
Nodes that need web content to progress are stuck until this exists.

**Target extraction from summaries not working reliably**
The summarizer is supposed to emit `new_targets` (additional URLs or search
queries to enrich the node further). In practice it rarely fires usefully.
Needs prompt work or a dedicated extraction step.

**`fetch_siren` enrichment**
SIREN data (headcount, legal form, registration date) is available but not
systematically pulled into the summary. Headcount in particular is a live
profile criterion that is currently almost never present in summaries.

---

## The underlying performance question

All of the above is machinery. The real question is whether the classifier is
any good. With ~40 reviews and ~50 eval results we have enough data to get a
first read — but we have not looked at it yet.

Hypothesis based on current reactions: the `discard` cases (commerce, pharma,
ESN, web-only) are probably well-covered by the profile's exclusion criteria and
the LLM handles them reliably. The `good` / `maybe` cases are fewer and likely
noisier — the positive criteria in the profile are less precise than the
exclusions.

If that hypothesis is right, the next profile update should focus on sharpening
the positive side, not adding more exclusions.
