# 2026-05-04 — Profile update prompt experiment

## What was done

### `prospect list` — display improvements

Replaced node_id with company name (from frontmatter) as the primary identifier.
Dropped the model/prompt_version tag — same for all nodes, not useful in a list.
Added last review reaction inline as a dim green trailing string.

### `anpe profile update --dry-run`

New command that formats the profile-update prompt from
[spec §2](../specs/33_ranking_eval_scraping.md) and prints it to stdout — ready
to paste into a web AI. No LLM call is made.

Each reaction line includes a 150-char truncated summary body indented below:

```
- [INFINITE ORBITS] TOULOUSE · 20-49 — "yes, space tech"
  INFINITE ORBITS is a Toulouse-based NewSpace PME specializing in in-orbit servicing...
```

29 reactions were included in the first run.

## Experiment — profile generation via Mistral Medium

Pasted the dry-run output into Mistral Medium. Result was a structured profile
with preferences (sectors, size, location, culture) and exclusions.

**What worked:**
- Hard exclusions correctly extracted: ecommerce, finance, pharma, infra.
- Size preference correctly inferred: 20–99 employees preferred.
- Top-tier companies correctly identified (Novelab, Infinite Orbits).

**What didn't:**
- Little Worker ("maybe") was over-interpreted as a positive signal — the LLM
  promoted a weak reaction to a preference.
- "Next Steps" and "Companies to Prioritize" sections appeared in the output —
  these are not durable criteria and should not go into `profile.md`. The profile
  should only contain criteria applicable to new, unseen companies.
- Summary snippets were noisy: H1 headings, NAF codes, LLM filler phrases crowded
  the 150-char window. The signal was there but degraded.

## Conclusion

The prompt structure works. The bottleneck is summary quality — thin or noisy
summaries produce weak reaction context, which produces a weaker profile update.
The prompt rewrite (spec §5) is the prerequisite.

For `profile.md`: manually extract the criteria-only sections (exclusions + size
+ sector preferences), strip the ranked company list and next-steps boilerplate.

## Next

- Rewrite the summarize prompt (spec §5 / implementation step 1).
- Manually edit `profile.md` with the clean criteria from this experiment.
- Once profile is populated, implement `score(node, profile)` (spec §3).
