# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run anpe              # run the interactive chat
uv run pytest            # all tests
uv run pytest tests/test_agent.py::test_agent_returns_response  # single test
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy anpe/        # type check
```

## Architecture

The agent is a pydantic-ai `Agent` instance defined as a module-level singleton in `anpe/agent.py`. It uses `OpenAIChatModel` pointed at OpenRouter's OpenAI-compatible API (`https://openrouter.ai/api/v1`). The model and API key come from `anpe/config.py` via `pydantic-settings`, which reads `.env`.

The CLI (`anpe/cli.py`) is a single click command that runs an async REPL loop. It imports the agent singleton directly.

**Adding tools:** decorate functions with `@agent.tool` in `agent.py` (or a separate `tools.py` imported there).

**Adding CLI subcommands:** convert `chat()` in `cli.py` to a `click.group()` and register subcommands.

## Testing

Agent tests use `pydantic-ai`'s `TestModel` via `agent.override(model=TestModel())` — no real API calls are made. `asyncio_mode = "auto"` is set in `pyproject.toml` so `@pytest.mark.asyncio` is optional but kept for clarity.

## LLM provider

OpenRouter is used as a drop-in OpenAI-compatible provider. Any model slug from OpenRouter can be set via `OPENROUTER_MODEL` in `.env`. Default is `openai/gpt-4o-mini`.
