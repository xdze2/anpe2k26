---
status: draft
---

# Principles

High-level design. How the vision translates into a system. what are the big components, how the interact. No detail.s

## Data vault

All user data lives in a single directory, owned and controlled by the user (private user git repo).

It contains:

- the user profile — what the user is looking for (target roles, preferred company sizes, sectors, dealbreakers,...etc)
- Data about nodes (aka companies):
  - fetched raw data
  - fetched data log and status
  - an information summary (one per node)
- chat logs

## Node information summary

Contains:

- information relevant to the user about the node
- next possible fetch target
- gathering status: done, discared, pending

## Enrichment workflow: fetch → eval → summarize

Enrichment dispatcher `enrich_node(seed_id)`:

- next_fetch_target(node_summary) -> (fetch_tool, uri)
- fetch(fetch_tool, uri) -> raw_data, log fetch_status
- eval(raw_data, user profile, [node_summary]) -> log eval status, new summary, rank_delta (mismatch between user rank and LLM perception)

Evaluation step is done by a LLM.

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

- A AI chat with an IA Agent is main user interface and interaction loop

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
