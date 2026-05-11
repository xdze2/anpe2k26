# ANPE-2k26

Personal job-search assistant for discovering companies you don't know exist yet.
Built with [pydantic-ai](https://ai.pydantic.dev/) and [Mistral AI](https://mistral.ai/).

## Quickstart

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url>
cd anpe2k26
uv sync
cp .env.example .env   # then add your MISTRAL_API_KEY
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
├── cli.py            # click CLI entry point
├── config.py         # pydantic-settings (.env)
├── profile.py        # user search profile read/write
├── clients/          # external API wrappers (SIREN, DDG)
├── engine/           # orchestration: queue, runner, vault, rate gate
├── steps/            # ANPE business logic: step classes (*_step.py)
│   │                 # and pure domain functions (*_fn.py)
│   └── bootstrap/    # company listing pipeline
└── tools/            # NAF codes, geocoding
tests/
docs/
├── specs/            # vision, design, usage examples
└── dev_log/          # session notes and decisions
```

User data (companies, profile, logs) lives in `user_data/` — gitignored.

## More

- [Vision and goals](docs/specs/10_vision.md)
- [Full spec index](docs/specs/README.md)
