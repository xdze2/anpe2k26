# USER_DATA_DIR as config constant — 2026-05-08

## What was done

Centralized the user data directory path in `anpe/config.py` so it can be
renamed on disk without touching source code.

### Changes

- `anpe/config.py`: added `user_data_dir: Path = Path("user_vault")` to
  `Settings` and a module-level `USER_DATA_DIR = settings.user_data_dir`.
  Set via `USER_DATA_DIR` env var (pydantic-settings convention).

- `anpe/node_dir.py`: replaced `Path(__file__).parent.parent / "user_data"`
  with `from anpe.config import USER_DATA_DIR`.

- `anpe/profile.py`: same replacement, removed private `_USER_DATA_DIR` alias.

- `anpe/cli.py` (`prospect seed`): import from `anpe.config` instead of
  `anpe.node_dir`.

- `anpe/cli.py` (`bootstrap run`): replaced `Path.cwd() / "user_data" / ...`
  with `USER_DATA_DIR / ...`. `cache_dir` remains at `cache_data/bootstrap_cache`
  (separate root-relative path, not under `USER_DATA_DIR`).

## Next

More bootstrap command cleanup (user's remaining points).
