---
status: draft_for_v2
---

# Project Vision

## What it is

_ANPE-2k26_ is a personal job-search assistant that helps you discover companies.

It is a research tool: it accumulates knowledge about companies over time, learns what you care about, and helps you triage a large candidate space down to a short list of genuine prospects.

The motivating problem is that the hardest part of a job search isn't evaluating companies you already know — it's finding the ones you don't know exist yet. The right company for you probably has no active job posting today. It may be a 5-person consultancy doing AI integration for the wine industry near Bordeaux, or a startup you've never heard of.

How an IA LLM could save you hours of web searching and not getting lost.

## How it works

Brute force approach -- the SIRENE dateset (France gouv) offers a different kind of input: an exhaustive register of every company in France. Filtered by sector and geography, it returns companies you've never encountered, some of which may be exactly what you're looking for. This is what makes discovery possible — an external, systematic source capable of genuine surprise.

The process starts with a **bootstrap**: pull an initial batch of candidates from SIRENE — raw seeds with almost no signal beyond sector and location. Then **refinement loops**: each loop adds a layer of information to some candidates (web search and website query), updates your profile from **your reactions**, and surfaces the strongest matches. The loop repeats across sessions. Each iteration, the profile sharpens and the signal-to-noise ratio improves.

User reactions feed back into the loop. When you say "DataVin looks interesting" or "too big, not what I want," the agent updates your search profile and adjusts how it evaluates the next batch. Over sessions, the profile sharpens — fewer irrelevant results, more of what you're actually looking for.

## Core ideas

**Brute-force discovery, intelligent triage.** Start with the full census, filter by geography and sector, then use enrichment + LLM evaluation to narrow to what matters. The hard work is in the triage layer, not the discovery layer.

**Active learning from user feedback.** The agent's user profile is a living document. Each reaction (interest, rejection, a comment about company size or culture) updates it. The profile is the memory that makes each session smarter than the last.

**LLM always in the evaluation loop.** Raw data (SIRENE JSON, DDG snippets, website HTML) is never shown directly to the user. An LLM eval step always interprets it first — extracting what's relevant, checking against the profile, deciding whether the information is new and whether it changes the match verdict.

**File-based, local, owned by you.** All data lives in a single directory. No database, no cloud sync. It can be backed up as a plain git repo. Every piece of raw data and every eval output is kept — the pipeline is fully replayable and auditable.

**Human in the loop.** The goal is a tool that amplifies your judgment, not one that replaces it. It asks before running expensive enrichment steps. Evolving dataset, the data pile ups and get updated.

## Why this project exists

It is a learning project — learning by building. Both to learn working with Claude code,
and to build data processing pipeline from LLM agents.

## Tech stack

Python 3.12, uv, pydantic-ai. LLM models from Mistral AI.
