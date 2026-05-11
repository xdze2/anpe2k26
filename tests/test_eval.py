"""Tests for anpe/steps/eval_fn.py."""

import json
from unittest.mock import MagicMock, patch

from anpe.steps.eval_fn import EvalResult, EVAL_VERSION, llm_eval


def test_eval_version_is_six_chars():
    assert len(EVAL_VERSION) == 6
    assert EVAL_VERSION.isalnum()


def test_llm_eval_returns_eval_result():
    data = {"score": "good", "fit": "small team, clean product", "dealbreakers": [], "uncertainty": "low"}
    with patch("anpe.clients.mistral.mistral_complete", return_value=json.dumps(data)):
        result = llm_eval(
            summary="A 20-person SaaS company in Toulouse building embedded AI.",
            profile="Looking for small PME, clean product, no ESN.",
        )

    assert isinstance(result, EvalResult)
    assert result.score in ("good", "maybe", "discard", "enrich")
    assert isinstance(result.fit, str) and result.fit
    assert isinstance(result.dealbreakers, list)
    assert result.uncertainty in ("low", "medium", "high")


def test_llm_eval_discard():
    data = {"score": "discard", "fit": "ESN with no own product", "dealbreakers": ["ESN"], "uncertainty": "low"}
    with patch("anpe.clients.mistral.mistral_complete", return_value=json.dumps(data)):
        result = llm_eval(
            summary="Large ESN, 500 employees, staff augmentation only.",
            profile="Looking for small PME, clean product, no ESN.",
        )

    assert result.score == "discard"
    assert result.dealbreakers == ["ESN"]
