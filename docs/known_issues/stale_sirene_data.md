# Known issue: stale SIRENE data for known companies

## Problem

When `search_companies` discovers a company already in `anpe_data/companies/`, the tool skips it ("never overwrite"). If the company's address, NAF code, or name has changed in SIRENE since discovery, the local file silently lags behind.

## Why it's acceptable for now

SIRENE data is stable in practice (legal name, NAF, address rarely change). Discovery is the primary use case; keeping user-written Notes and Historique intact takes priority over refreshing metadata.

## When it matters

- A company relocates or changes its legal name
- NAF code is corrected after an official reclassification

## Future fix

Add an `update_company_metadata(siren)` tool that diffs SIRENE against the frontmatter, proposes changes, and appends an entry to `## Historique` if accepted. Never touch the Notes section.
