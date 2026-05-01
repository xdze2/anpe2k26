# Process

## docs/ layout

```
docs/
├── specs/          # project specification (this folder)
├── dev_log/        # one file per work session
├── inbox/          # raw ideas, not yet examined
├── known_issues/   # known bugs or limitations, not yet acted on
└── references/     # external docs, API specs, research material
```

`docs/specs/` is the project specification. Files cover key parts of the app, numbered for rough reading order.

## specs/

Files are numbered with a tens-based scheme: `10_`, `20_`, `30_`... The tens digit groups related topics; the units digit allows sub-parts (`41_`, `42_`) without renumbering. Numbers reflect reading order, not priority.

## Spec file lifecycle

One file per key part, number prefix in filename (`40_`, `41_`...).

Status tracked in frontmatter:

```markdown
---
status: draft | active | done
---
```

- **draft** — being written, not yet committed to
- **active** — being built against right now
- **done** — implemented, kept as reference

Files stay in `docs/specs/` regardless of status.

`docs/inbox/` is pre-status: raw ideas, not yet examined.

## Dev log

One file per work session in `docs/dev_log/`:

```
log_ISODATE_slug.md
```

- `ISODATE` — compact ISO 8601 with hour: `20260430T1430`
- `slug` — 2–4 words on the session topic

Logs are freeform — the goal is to capture the building story: what was tried, what changed, and why.
