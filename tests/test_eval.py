"""Tests for anpe/prospect/eval.py."""

import pytest
from pydantic_ai.models.test import TestModel

from anpe.prospect.eval import EvalResult, EVAL_VERSION, _agent, llm_eval


def test_eval_version_is_six_chars():
    assert len(EVAL_VERSION) == 6
    assert EVAL_VERSION.isalnum()


@pytest.mark.asyncio
async def test_llm_eval_returns_eval_result():
    with _agent.override(model=TestModel(custom_output_args={"score": "good", "fit": "small team, clean product", "dealbreakers": [], "uncertainty": "low"})):
        result = await llm_eval(
            summary="A 20-person SaaS company in Toulouse building embedded AI.",
            profile="Looking for small PME, clean product, no ESN.",
        )

    assert isinstance(result, EvalResult)
    assert result.score in ("good", "maybe", "discard", "enrich")
    assert isinstance(result.fit, str) and result.fit
    assert isinstance(result.dealbreakers, list)
    assert result.uncertainty in ("low", "medium", "high")


@pytest.mark.asyncio
async def test_llm_eval_discard():
    with _agent.override(model=TestModel(custom_output_args={"score": "discard", "fit": "ESN with no own product", "dealbreakers": ["ESN"], "uncertainty": "low"})):
        result = await llm_eval(
            summary="Large ESN, 500 employees, staff augmentation only.",
            profile="Looking for small PME, clean product, no ESN.",
        )

    assert result.score == "discard"
    assert result.dealbreakers == ["ESN"]
