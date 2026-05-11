# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Starting a session

Read the 2 most recent dev log entries before doing anything else:

```bash
ls docs/dev_log/ | tail -2   # find the latest entries
```

It captures context, decisions, and next steps that aren't in git history.

## Commands

```bash
uv run pytest            # all tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy anpe/        # type check
```
