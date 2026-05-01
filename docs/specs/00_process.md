
- Code implementation is written by Claude

docs/ is the project specification



## Feature spec lifecycle

One file per feature, numerotation in file name "41_", "42_"...etc

status tracked in frontmatter:

```markdown
---
status: draft | active | done
---
```

- **draft** — being written, not yet committed to
- **active** — being built against right now
- **done** — implemented, kept as reference

Files stay in `docs/design/` regardless of status.
`ideas/` is pre-status: nothing there has a spec yet.


## Dev log format
keep track of work session, exploration and backtracking...


One file per session, in `dev_log/`:

```
log_ISODATE_slug.md
```

- `ISODATE` — compact ISO 8601 with hour: `20260430T1430`
- `slug` — 2-4 words describing the session topic

Example: `log_20260430T1430_company-enrichment-pipeline.md`

### File structure

```markdown
# YYYY-MM-DD — Session title

## What we worked on
## Why / context
## What we learned / decisions made
## Dead ends or things tried that didn't work
## Next
```