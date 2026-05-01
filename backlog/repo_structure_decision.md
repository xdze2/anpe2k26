# ANPE — Repository Documentation Structure

Decision record for how project documentation is organized.
To be applied when the current `backlog/` folder is reorganized.

---

## Agreed structure

```
docs/
  product/          ← goals, user scenarios, known issues (what a client cares about)
  design/           ← architecture and component specs (internal)
  reference/        ← external APIs, data sources (internal); each subfolder has an index.md
  dev_log/          ← dated narrative entries: why we tried things, what we learned, dead ends
  process.md        ← how we work: conventions, workflow, tooling decisions
ideas/              ← low-friction, no-commitment scratchpad (pre-spec)
```

`backlog/` disappears — its contents migrate into the above.

---

## Feature spec lifecycle

One file per feature, status tracked in frontmatter:

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

---

## Dev log format

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

---

## Makefile (deferred)

Add a `make status` or `make design` target once the number of files makes
the grep annoying to type:

```bash
grep -r "^status:" docs/design/
```
