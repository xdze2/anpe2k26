# ANPE-2k26: L'Assistant Numérique Pour l'Emploi


- IA Agent
- use https://pydantic.dev/

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
uv run python main.py
```