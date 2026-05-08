"""Step registry — single source of truth for all engine steps."""

from __future__ import annotations

from anpe.engine.steps.base import Step


def _load() -> dict[str, Step]:
    from anpe.engine.steps.bootstrap import BootstrapStep
    from anpe.engine.steps.eval import EvalStep
    from anpe.engine.steps.fetch_ddg import FetchDdgStep
    from anpe.engine.steps.fetch_siren import FetchSirenStep
    from anpe.engine.steps.summarize_ddg import SummarizeDdgStep

    steps: list[Step] = [BootstrapStep(), FetchSirenStep(), FetchDdgStep(), SummarizeDdgStep(), EvalStep()]
    return {s.name: s for s in steps}


# Module-level singleton — imported by CLI and runner setup.
STEPS: dict[str, Step] = _load()
