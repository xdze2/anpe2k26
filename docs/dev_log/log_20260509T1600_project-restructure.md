# Project restructure: steps/, engine/base.py, _step/_fn suffixes

Date: 2026-05-09

## What changed

Major reorganisation of the package layout. No logic was modified.

### New top-level structure

```
anpe/
  clients/      external API wrappers (unchanged)
  engine/       orchestration only — queue, runner, vault, rate gate
  steps/        ANPE business logic
  cli.py
```

### engine/steps/ → steps/ + engine/base.py

`anpe/engine/steps/` was a mixed bag: the `Step` protocol and error types
(`base.py`) belong to the engine, while the concrete step classes are domain
code. Split accordingly:

- `engine/steps/base.py` → `engine/base.py`
- All concrete step files → `steps/`

### anpe/bootstrap/ and anpe/prospect/ dissolved

Both packages were domain code misplaced outside `steps/`:

- `bootstrap/{pipeline,filter,search}.py` → `steps/bootstrap/`
- `prospect/eval.py`, `summarize.py`, `seed.py`, `types.py`, `registry.py` → `steps/`
- `prospect/review.py` — replaced by the new `steps/review_step.py` (committed
  separately just before this session)

### Naming conventions: _step and _fn suffixes

Two kinds of modules now coexist in `steps/` — step classes (engine glue) and
pure domain functions (LLM calls, filtering, slugification). Made the
distinction explicit with suffixes:

- `*_step.py` — contains the `Step` class: `scan`, `work`, engine imports
- `*_fn.py` — pure functions, no engine concepts

Final file list:

```
steps/
  bootstrap_step.py      bootstrap/pipeline.py
  eval_step.py           bootstrap/filter.py
  eval_fn.py             bootstrap/search.py
  fetch_ddg_step.py
  fetch_siren_step.py
  summarize_ddg_step.py
  summarize_fn.py
  review_step.py
  seed_fn.py
  types.py
  registry.py
  api_throttles.py
```

## Status

81 tests pass, unchanged.

## What remains

- `anpe/cli.py` still has a `prospect review` command stub that prints a
  placeholder — needs wiring to `ReviewStep` via the runner.
- `node_dir.py` is still referenced in cli.py; it's legacy and can be removed
  once the remaining `prospect` CLI commands are ported or dropped.
