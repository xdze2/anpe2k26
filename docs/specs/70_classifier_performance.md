---
status: roadmap
---

# Classifier performance analysis

This is not a spec for a finished feature. It is a roadmap for understanding
whether the pipeline works — whether the LLM eval agrees with the user's actual
judgments, and whether the profile captures the right features.

---

## The core question

The system is a **binary classifier**: each company is either a match or not.
The LLM eval is the classifier. The user profile is the feature spec. The user
reactions are the ground truth.

Right now we have ~40 user reactions and ~50 eval results. We do not know:

- How often the LLM agrees with the user.
- In which direction it fails (false positives? false negatives?).
- Whether the profile criteria are actually driving the decisions, or whether
  the LLM is classifying on something else.
- Which profile criteria never fire because the data is never there to trigger them.

Without this, improving the profile is guesswork.

---

## Step 1 — Confusion matrix

**What:** compare `eval score` against `user reaction` for every node that has both.

**The alignment problem:** reactions are free text ("no, commerce only", "yes",
"why not but no jobs"). They are not `good/maybe/discard`. Before building the
matrix you need to map reactions to a binary label.

Options:
- Hand-label (fast, ~40 rows, authoritative).
- LLM-classify the reactions against a simple rubric ("yes/no/unsure") — cheap
  and reproducible, but introduces a second LLM judgment to validate the first.

Recommended: hand-label, store as a `label` field in a small JSON/CSV beside
the spec or in `user_data/`. This is ground truth — do not outsource it.

**Expected output:**

```
              eval: good  eval: maybe  eval: discard  eval: enrich
user: yes        ?           ?              ?              ?
user: no         ?           ?              ?              ?
user: unsure     ?           ?              ?              ?
```

**Hard part:** the sample is small and heavily skewed toward `no` (most companies
are not a match). Precision on `good` matters more than overall accuracy —
a false positive wastes review time; a false negative loses a real opportunity.

**What to watch for:**
- High `discard` agreement → the profile's exclusion criteria work.
- `good` / `maybe` misalignment → the positive criteria are too weak or too vague.
- `enrich` on nodes the user said `yes` to → the profile is asking for information
  the pipeline never surfaced.

---

## Step 2 — Profile coverage analysis

**What:** for each eval result, which profile criteria were actually cited in
`fit` or `dealbreakers`? Which criteria were never mentioned across all evals?

**Why it matters:** the profile lists ~10-20 criteria. If 3 criteria account for
90% of `discard` decisions, the others are dead weight — or worse, they are live
but never triggered because the summaries never contain the relevant data.

Two distinct failure modes:
1. **Criterion never fires** because the summary data is always missing → enrichment
   gap. The node gets `maybe` or `enrich` where it should be `good` or `discard`.
2. **Criterion fires but is vague** → LLM invents a signal. The `fit` sentence
   will be plausible but not traceable to anything in the summary.

**Expected output:** a table of profile criteria × how often they appear in eval
outputs, with a flag for criteria that never appear.

**Hard part:** the LLM paraphrases. "ESN / consulting shop" in the profile becomes
"IT services firm with no product" in `fit`. Matching paraphrases to criteria
requires either fuzzy string matching or a second LLM pass. Neither is clean.
Start with manual inspection of the 50 existing results — patterns will emerge
before you need automation.

---

## Step 3 — Enrichment coverage

**What:** for nodes where the user said `yes` or `maybe`, what information is
absent from the summary that could have strengthened the eval signal?

This is the complement of Step 2: instead of looking at profile criteria, look
at what the summary is missing. The questions are:

- Is headcount present? (small vs. large matters for the profile)
- Is tech stack mentioned?
- Is there a job offer linked?
- Is the domain clear enough to apply a dealbreaker?

**Why it matters:** the classifier can only be as good as the features fed to it.
If headcount is missing in 60% of summaries, a profile criterion based on company
size is not testable.

**Expected output:** per-field coverage rate across all summaries. Flag fields
that are structurally absent (not in the fetch output) vs. present but not
extracted by the summarizer.

---

## Dependencies and order

These three analyses share the same data (reviews + eval results + summaries)
and can be done in parallel, but Step 1 is the blocker: without a ground truth
label for each reaction, Steps 2 and 3 have no outcome variable to correlate
against.

Suggested order:
1. Hand-label the 40 reactions → `user_data/ground_truth.json` or similar.
2. Build the confusion matrix (a script, not a command).
3. Inspect the misclassified nodes manually — this gives more signal than the
   matrix alone.
4. Run the profile coverage analysis against the same misclassified nodes first.
5. Add enrichment coverage last, once you know which criteria are worth feeding.

---

## What success looks like

Not a number. The goal is to be able to answer:

- "The eval is reliable for `discard` (>90% agreement) but noisy for `good`."
- "The profile's size criterion never fires because headcount is missing."
- "3 of the 5 positive criteria in the profile have zero coverage in the summaries."

Those answers drive concrete changes: tighten the profile, add a headcount
extraction step, adjust the eval prompt. Without them, all profile edits are
intuition.
