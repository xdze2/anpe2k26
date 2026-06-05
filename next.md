# Next — ideas and directions

## UX improvements (web app)

### "Next action" field in the review form
The current `reaction` (interested / not_interested / more_data) captures sentiment.
A separate **next action** field would capture intent and make the screening workflow
actionable:

- look for job offers
- apply
- no offer now, follow up later
- contact directly (HR, manager, etc.)

Stored alongside `reaction` in `review_*.json`. Rendered as radio buttons or a compact
select in the detail panel.

### Flag broken next-target links
`new_targets` from `summarize_ddg_*.json` are rendered as clickable links but are
often broken (the LLM extraction may be unreliable — see dev log). Add a small
"broken" flag button per link that POSTs to a new endpoint and marks the target in the
JSON. Helps identify systemic issues with the extraction.

---

## Multiple user profiles

`user_profile.md` is a single file used by the eval step. Supporting multiple profiles
would allow searching along different axes simultaneously (e.g. different roles, cities,
or seniority levels).

Rough design:
- profiles live in a `profiles/` dir (or named `user_profile_*.md`)
- `eval` step takes a `--profile <name>` flag
- `eval_*.json` output tags which profile was used
- table view can filter/group by profile

---

## Firefox extension (capture mode)

Originally considered as "open links without focus switch", the real value is the
opposite: **feed the LLM context it can't reach on its own** — pages behind login,
JS-rendered content, company intranets.

A minimal WebExtension (dev mode, no store publish needed):
- "Capture page" button sends current tab's text content to the Flask app
  (`POST /node/<node_id>/capture` or a new inbox endpoint)
- Content is saved in the node dir and can be used as extra input to summarize/eval
- Fills the gap between automated enrichment and human browsing

This directly supports the "augmented screening" use case.

---

## Performance / "on the fly" evals

If evals feel slow, likely causes:
- LLM latency per node (sequential, no parallelism)
- Full pipeline re-run even when only eval is needed

Options:
- Run evals in parallel across nodes (already has a rate gate, check if it's the bottleneck)
- Faster/cheaper model for a first-pass score (then full eval on promising ones)
- Streaming eval results to the web UI as they complete

Worth profiling before optimizing — measure where time is actually spent.

---

## Misc / longer term

- Demo: screenshots, short video of the screening workflow
- Map view of toulouse companies by tech domain (`faire une carte`)
- More nuanced classification — toward a ranking rather than hard score buckets
