# ANPE-2k26

Personal job-search assistant for discovering companies you don't know exist yet.
Built with [pydantic-ai](https://ai.pydantic.dev/) and [OpenRouter](https://openrouter.ai/).

## Quickstart

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url>
cd anpe2k26
uv sync
cp .env.example .env   # then add your OPENROUTER_API_KEY
```

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
├── agent.py          # pydantic-ai agent (singleton)
├── cli.py            # click CLI entry point
├── config.py         # pydantic-settings (.env)
├── profile.py        # user search profile read/write
├── tools/
│   ├── geo_api.py    # geocoding
│   └── naf.py        # NAF code search
└── data/
    └── naf_codes.csv
tests/
docs/
├── specs/            # vision, design, usage examples
└── dev_log/          # session notes and decisions
```

User data (companies, profile, logs) lives in `user_data/` — gitignored.

## More

- [Vision and goals](docs/specs/10_vision.md)
- [Usage examples](docs/specs/20_usage_examples.md)
- [Architecture and design](docs/specs/40_design.md)
- [Enrichment pipeline](docs/specs/42_enrichment_design_v2.md)
- [Full spec index](docs/specs/README.md)
