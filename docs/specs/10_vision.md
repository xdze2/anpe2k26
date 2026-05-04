---
status: active
---

# Project Vision

## What it is

_ANPE-2k26_ is a personal job-search assistant that helps you discover companies.

It is a research tool: it accumulates knowledge about companies over time, learns what you
care about, and helps you triage a large candidate space down to a short list of genuine
prospects.

The motivating problem is that the hardest part of a job search isn't evaluating companies
you already know — it's finding the ones you don't know exist yet. The right company for
you probably has no active job posting today. It may be a 5-person consultancy doing AI
integration for the wine industry near Bordeaux, or a startup you've never heard of.
An LLM assistant can save you hours of unfocused web searching and help you stay on track.

## An exploration assistant

The SIRENE dataset contains every registered company in France — tens of thousands of
candidates once filtered by sector and geography. But SIRENE is purely administrative:
a SIREN number, a NAF code, a location, (plus other legal data). No website, no description, no
sense of what the company actually does, and if you would be interested to work with them. There is no pre-existing signal to query
against — you can't search for "interesting AI startup near Bordeaux" because that field doesn't exist.

The challenge is not finding candidates (aka company names) — they are all already there. The challenge is
navigating a space that is too large to evaluate directly, and too undifferentiated to
filter by relevance before you've done the work of enriching it.

Also it is an exploration process, we don't known what we are looking for yet, it will be a surprise.

Enrichment is how you generate signal: fetch a website, run a web search, ask an LLM
to summarize what it found. Each step transforms a dry administrative record into
something you can actually judge. But enrichment has a cost — in time, in API calls, on noise accumulation —
so it can't be applied blindly to every candidate.

This is why the assisitent is structured as an exploration loop rather than a batch
process. At each iteration, a small number of candidates get enriched, evaluated
against your profile, and surfaced to you. Your reactions — interest, rejection, a
remark — update the profile and guide which candidates are worth exploring next.
Over sessions, the explored region grows, the profile sharpens, and the signal-to-noise
ratio improves.

## Core ideas

**Brute-force discovery, intelligent triage.** Start with the full census, filter by
geography and sector, then use enrichment and LLM evaluation to narrow to what matters.
The hard work is in the triage layer, not the discovery layer.

**Active learning from user feedback.** The agent's user profile is a living document.
Each reaction — interest, rejection, a comment about company size or culture — updates it.
The profile is the memory that makes each session smarter than the last.

**LLM always in the evaluation loop.** Raw data (SIRENE JSON, DDG snippets, website HTML)
is never shown directly to the user. An LLM eval step always interprets it first —
extracting what's relevant, checking against the profile, deciding whether the information
is new and whether it changes the match verdict.

**File-based, local, owned by you.** All data lives in a single directory. No database,
no cloud sync. It can be backed up as a plain git repo. Every piece of raw data and every
eval output is kept — the pipeline is fully replayable and auditable.

**Human in the loop.** The goal is a tool that amplifies your judgment, not one that
replaces it. The agent asks before running expensive enrichment steps. The dataset grows
over time and gets progressively refined.

## Why this project exists

A learning project — learning by building: working with Claude Code, and building a data
processing pipeline from LLM agents.

## Tech stack

Python 3.12, uv, pydantic-ai. LLM models from Mistral AI.
