"""Step registry — single source of truth for all engine steps."""

from __future__ import annotations

from anpe.engine.base import AsyncStep, Step


def _load() -> dict[str, Step]:
    from anpe.steps.bootstrap_step import BootstrapStep
    from anpe.steps.eval_step import EvalStep
    from anpe.steps.fetch_ddg_step import FetchDdgStep
    from anpe.steps.fetch_siren_step import FetchSirenStep
    from anpe.steps.review_step import ReviewStep
    from anpe.steps.summarize_ddg_step import SummarizeDdgStep

    async_steps: list[AsyncStep] = [BootstrapStep(), FetchSirenStep(), FetchDdgStep(), SummarizeDdgStep(), EvalStep()]
    steps: list[Step] = [*async_steps, ReviewStep()]
    return {s.name: s for s in steps}


# Module-level singleton — imported by CLI and runner setup.
STEPS: dict[str, Step] = _load()
