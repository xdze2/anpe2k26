# 2026-05-01 — POC enrichment implementation

## What changed

Built the full enrichment POC from scratch: fetch registry, node storage, LLM
summarization, and CLI commands.

### anpe/enrich/

- `registry.py` — `FETCH_TOOLS: dict[str, Callable[[str], str]]`, currently `{"ddg": ddg_search}`.
  Adding a new fetch method = one dict entry.
- `tools/ddg.py` — minimal DuckDuckGo tool via `ddgs` lib, returns plain text, raises on no results.
- `summarize.py` — `EnrichResult` pydantic model (`status`, `summary`, `new_targets`) +
  `llm_summarize()` as a pydantic-ai agent with structured output. Uses same OpenRouter
  provider as the chat agent. Hardcoded intent for now:
  *"We are looking for small French tech companies doing AI or software work."*
- `pipeline.py` — `enrich_step()`: pops one pending fetch, runs it, saves raw data,
  calls LLM, writes summarize log, updates summary and re-queues new targets.
  Logs each step to stdout (fetch size, LLM status, errors).

### anpe/node_dir.py

Disk interface for one node (`user_data/nodes/<node_id>/`). Two append-only event logs:

- `fetch.jsonl` — fetch log / cache. Events: `put` / `done` / `error`. Each target has
  a short random `uid`. `done` carries a `raw_file` pointer. Acts as a cache: already-done
  targets can be re-summarized without re-fetching (e.g. after a prompt change).
- `summarize.jsonl` — one entry per LLM call: model, status, summary, new_targets,
  linked to the fetch via `fetch_uid`.
- `raw_data/` subdir for raw fetch files.
- `summary.md` — current summary, overwritten on each update.

### CLI

`anpe` converted to a `click.group`. Three subcommands:
- `anpe chat` — interactive chat (was the default)
- `anpe add_target NODEID TOOL KEYWORD` — seed a node's fetch queue
- `anpe enrich NODEID` — run one fetch+summarize step

### Tested on real data

- `veolia` — correctly returned `not_relevant` (multinational, not a small tech company)
- `syn` (query: "synapse toulouse") — noisy DDG results (theatre company, association),
  LLM correctly identified Synapse Développement (AI agency, Toulouse, 1994) and produced
  a clean summary. Did not propose follow-up targets — prompt tuning needed.

## Next

- Prompt tuning: LLM should propose follow-up targets more aggressively (e.g. website URL found in DDG results)
- Test on more companies to calibrate `not_relevant` threshold
- Add `--rerun-summarize` mode to replay fetch cache through a new prompt
