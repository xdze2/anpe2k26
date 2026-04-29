# ANPE — Design Document

## Purpose

ANPE is a personal job-search assistant. Its primary goal is to help the user scan companies (or projects, people) and identify which ones match what he is looking for. The agent accumulates knowledge over time: it learns the user's preferences, gathers data on companies from the web, and records the user's reactions to each one.

---

## Architecture overview

```
cli.py          ← entry point, async REPL, rich rendering
  │
  └── agent.py  ← pydantic-ai Agent singleton, tools registered here
        │
        ├── config.py          ← pydantic-settings, reads .env
        ├── profile.py         ← read/write user_data/profile.md
        └── tools/
              └── naf.py       ← NAF code bidirectional lookup (CSV)
```

**Runtime:** Python 3.12, uv, pydantic-ai. LLM calls go through OpenRouter (OpenAI-compatible API), so any model slug can be swapped via `.env`.

---

## Data flow per session

```
startup
  │
  ├── profile.py reads user_data/profile.md
  │     → injected verbatim into system prompt (always in context)
  │     → if file missing: system prompt instructs agent to run onboarding
  │
user turn
  │
  ├── agent reasons, may call tools:
  │     read_search_profile   → returns raw profile text
  │     update_search_profile → full-rewrite of profile.md
  │     naf_lookup            → code → label
  │     naf_search            → keywords → top-10 matching codes
  │
  └── agent streams response → cli.py renders via rich Live
```

Tool calls are shown in the terminal as they fire (`⟳ tool_name` spinner line).

---

## Persistent storage

All persistence lives in `user_data/` (gitignored, never committed).

### `user_data/profile.md`

The user's search profile. Loaded once at startup and injected into the system prompt. Updated by the agent via `update_search_profile` during conversation (e.g. after the user reacts to a company).

**Design decisions:**
- **Full rewrite, not append.** Append-only would let contradictions accumulate across sessions. The agent receives the old content in context and synthesizes a new version.
- **Word-count enforcement.** `write_profile` returns a warning to the agent if content exceeds 400 words. The system prompt also instructs the agent to synthesize rather than accumulate. Two layers: instruction + feedback.
- **In system prompt, not on-demand.** The profile is short by design, so the token cost of always including it is low. It ensures the agent never forgets it when scoring companies.

Suggested sections (freeform markdown, not enforced):
```
# Search Profile
## What I'm looking for
## Dealbreakers
## Context
```

### `user_data/companies/`

One file per company, loaded on demand (not in system prompt). Intended to hold:
- scraped data (web, API)
- user feedback ("interesting", "too big", "wrong sector")
- agent notes

**Not yet implemented.** See next steps below.

---

## Tools

| Tool | Type | Description |
|---|---|---|
| `read_search_profile` | `tool_plain` | Returns `user_data/profile.md` content |
| `update_search_profile(new_content)` | `tool_plain` | Full rewrite of profile, warns if > 400 words |
| `naf_lookup(code)` | `tool_plain` | NAF code → activity label |
| `naf_search(keywords)` | `tool_plain` | Free-text → top-10 matching NAF codes |

`tool_plain` means no `RunContext` injection — these tools are stateless functions. Use `@agent.tool` (with context) only if the tool needs access to run metadata.

---

## Configuration

`anpe/config.py` uses pydantic-settings. Values come from `.env`:

```
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-4o-mini   # any OpenRouter slug
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

The model is a module-level singleton (`_model`) instantiated once at import time. The agent is also a module-level singleton (`agent`). Both are safe because the CLI runs a single process per session.

---

## CLI

`cli.py` runs a `prompt_toolkit` async REPL. Each user turn calls `agent.run()` with an `event_stream_handler` to capture `FunctionToolCallEvent` and show tool names in a rich spinner while the LLM is thinking. Output is non-streaming (full response printed after completion).

**No conversation history persistence.** Each session starts fresh from the system prompt + profile. Company files will provide continuity for company-specific context when that feature is built.

---

## Testing

Tests use pydantic-ai's `TestModel` via `agent.override(model=TestModel())`. No real API calls. `asyncio_mode = "auto"` in `pyproject.toml`.

---

## Next steps

1. **Company store** — tools to create/read/update `user_data/companies/<slug>.md`. Schema: name, URL, scraped summary, NAF code, user rating, notes.
2. **Web research tool** — given a company name/URL, fetch and summarize relevant public info (website, LinkedIn, news).
3. **Scanning flow** — a mode where the agent works through a list of companies, presents each one, asks for user feedback, and updates the company file + optionally refines the profile.
