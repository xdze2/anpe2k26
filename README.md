# ANPE-2k26: L'Assistant Numérique Pour l'Emploi

- IA Agent built with [pydantic-ai](https://ai.pydantic.dev/)
- LLM provider: [OpenRouter](https://openrouter.ai/)

Code written with [Claude Code](https://claude.ai/code) (claude-sonnet-4-6) by Anthropic.

## Claude Code setup

Install the Pydantic AI skills plugin for Claude Code:

```bash
claude plugin marketplace add pydantic/skills
claude plugin install ai@pydantic-skills
```

## Installation

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url>
cd anpe2k26
uv sync
```

## Configuration

Copy the example env file and fill in your API key:

```bash
cp .env.example .env
```

Edit `.env`:

```
OPENROUTER_API_KEY=sk-or-...        # required — your OpenRouter API key
OPENROUTER_MODEL=openai/gpt-4o-mini # optional — any OpenRouter model slug
```

Get an API key at https://openrouter.ai/keys.

## Usage

```bash
uv run anpe        # interactive chat
uv run pytest      # run tests
uv run ruff check  # lint
uv run mypy anpe/  # type check
```

## Project structure

```
anpe/
├── agent.py    # pydantic-ai agent definition
├── cli.py      # click CLI entry point
└── config.py   # pydantic-settings configuration
tests/
└── test_agent.py
```
