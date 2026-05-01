---
status: draft
---

# Principles

High-level design. How the vision translates into a system.

## Data vault

All user data lives in a single directory, owned and controlled by the user (private user git repo). All as text files (markdown with frontmatter yaml, jsonl).

Two kinds of persistent state:

**User search profile** (`search_profile.md`) — description of what the user is looking for:
target roles, preferred company sizes, sectors, dealbreakers,...et

The agent reads it at startup and updates it as the user reacts to companies.

[TBD] Updates are full rewrites, not appends — contradictions don't accumulate.

**Company nodes** (`companies/node<SIREN>`) — one directory per candidate company. A node starts as a bare
seed from SIRENE (aka the SIREN code) and grows as information is collected. It
holds a human-readable summary of everything gathered so far, the user's triage verdict,
and freeform notes. Raw source data is stored separately and never deleted — the summary
view is always regenerable.

## Enrichment: fetch → eval → summarize

Every information fetch is followed by an LLM evaluation step, and summarization.

Raw data is never surfaced directly to the user, but stored for cache, replayability and debugging.

### Eval and summarization step

- done by a LLM model

Each eval covers three questions in sequence:

1. **Data quality** — did the fetch return usable content?
2. **Content value** — is there anything new and relevant here?
3. **Match delta** — does this change the assessment against the user's profile?

The Match delta and summarizatin is always relative to the user profile and to what was already known. The summary
it produces is not an objective description of the company — it is an interpretation
from the user's point of view.

Only information that is both new and relevant produces a written output. Confirmed negatives stop the pipeline early.

The pipeline is oriented toward positive matches:
among many candidates, few will be strong positives, so stopping early on negatives is the default.

The role of the summarization step is also to identify potiential next target for information retrieval.

### Information sources and cost

Sources are ordered by cost. Cheaper sources run first; expensive ones only after the
user has expressed interest.

| Source           | Cost                                             |
| ---------------- | ------------------------------------------------ |
| SIRENE API       | free, rate-limit friendly                        |
| Web search (DDG) | free, best first-pass for small French companies |
| Website fetch    | free, but fails on Cloudflare / JS-heavy sites   |
| Tavily search    | paid (1000 req/month quota) — post-interest only |
| ...              | ...                                              |

Each source has a fetch step and a paired eval step. Adding a new source always follows
the same pattern; no structural changes needed.

## Enrichment dispatcher

One entry point: `enrich_company(node_id)`. From the current state of a node (read from
the event log), it decides the next step to run, executes it, and appends the result.
One step per call — the agent can report progress, ask the user whether to continue,
and abort at any point.

All enrichment events are appended to a JSONL log. This log is the single source of
truth for enrichment state. It is append-only; nothing is ever deleted or overwritten.

## Triage

Each company carries a user verdict:

| Status       | Meaning                      |
| ------------ | ---------------------------- |
| `to_look_at` | candidate, not yet evaluated |
| `discarded`  | confirmed not relevant       |
| `good`       | interesting                  |
| `very_good`  | strong match                 |

The verdict is set by the user directly, or inferred by the agent from eval results
and the search profile. The agent proposes; the user confirms or corrects.

## Agent

A conversational agent (pydantic-ai) glues the tools together and handles user input.
Its tools are: read/write the search profile, read/update company nodes, and trigger
enrichment steps.

The agent operates in two modes:

- **Interactive** — responds to user requests in a chat loop.
- **Autonomous** — runs a batch of pending enrichment steps without user input
  (e.g. `uv run anpe enrich`). Stops and surfaces results that need user judgment
  (`unclear` verdicts, `blocked` fetches).

The eval model and the chat agent share no context. Eval steps run separately; the
agent reads their output files.
