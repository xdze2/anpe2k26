# Vision

## What it is

ANPE2k26 is a personal job-search assistant that helps you discover companies worth applying to — before you ever write a cover letter. It is not a job-board aggregator. It is a research tool: it accumulates knowledge about companies over time, learns what you care about, and helps you triage a large candidate space down to a short list of genuine prospects.

The motivating problem: the right company for you probably has no active job posting today. It may be a 20-person consultancy doing AI integration for the wine industry near Bordeaux, or a startup you've never heard of. Job boards won't surface it. You have to find it yourself.

## How it works

The hardest part of a job search isn't evaluating companies you already know — it's finding the ones you don't know exist yet. Your network has a ceiling. Searching by name only surfaces what you've already heard of. SIRENE offers a different kind of input: an exhaustive register of every company in France. Filtered by sector and geography, it returns companies you've never encountered, some of which may be exactly what you're looking for. This is what makes discovery possible — an external, systematic source capable of genuine surprise.

The process starts with a **bootstrap**: pull an initial batch of candidates from SIRENE — raw seeds with almost no signal beyond sector and location. Then **refinement loops**: each loop adds a layer of information to some candidates (web search, website, news), updates your profile from your reactions, and surfaces the strongest matches. The loop repeats across sessions. Each iteration, the profile sharpens and the signal-to-noise ratio improves.

User reactions feed back into the loop. When you say "DataVin looks interesting" or "too big, not what I want," the agent updates your search profile and adjusts how it evaluates the next batch. Over sessions, the profile sharpens — fewer irrelevant results, more of what you're actually looking for.

## Core ideas

**Brute-force discovery, intelligent triage.** Start with the full census, filter by geography and sector, then use enrichment + LLM evaluation to narrow to what matters. The hard work is in the triage layer, not the discovery layer.

**Active learning from user feedback.** The agent's user profile is a living document. Each reaction (interest, rejection, a comment about company size or culture) updates it. The profile is the memory that makes each session smarter than the last.

**LLM always in the evaluation loop.** Raw data (SIRENE JSON, DDG snippets, website HTML) is never shown directly to the user. An LLM eval step always interprets it first — extracting what's relevant, checking against the profile, deciding whether the information is new and whether it changes the match verdict.

**File-based, local, owned by you.** All data lives in a single directory (`anpe_data/`). No database, no cloud sync, no vendor lock-in. It can be backed up as a plain git repo. Every piece of raw data and every eval output is kept — the pipeline is fully replayable and auditable.

**Human in the loop.** The agent proposes; the user decides. It suggests NAF codes before calling SIRENE. It flags `unclear` cases rather than guessing. It asks before running expensive enrichment steps. The goal is a tool that amplifies your judgment, not one that replaces it.

## Why this project exists

It is also a learning project — learning by building. The goal is to explore what a personal LLM agent actually looks like when it accumulates knowledge, interacts with external APIs, and persists state across sessions — using pydantic-ai, file-based storage, and a local-first design philosophy.

## Tech stack

Python 3.12, uv, pydantic-ai. LLM calls via OpenRouter (OpenAI-compatible API). A separate cheaper model is used for eval steps.
