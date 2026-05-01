---
status: draft
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
