"""Tests for anpe/steps/eval_fn.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anpe.steps.eval_fn import EvalResult, EVAL_VERSION, llm_eval


def test_eval_version_is_six_chars():
    assert len(EVAL_VERSION) == 6
    assert EVAL_VERSION.isalnum()


def _mock_response(data: dict) -> MagicMock:
    response = MagicMock()
    response.choices[0].message.content = json.dumps(data)
    return response


@pytest.mark.asyncio
async def test_llm_eval_returns_eval_result():
    data = {"score": "good", "fit": "small team, clean product", "dealbreakers": [], "uncertainty": "low"}
    with patch("anpe.clients.mistral._client") as mock_client:
        mock_client.chat.complete_async = AsyncMock(return_value=_mock_response(data))
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
    data = {"score": "discard", "fit": "ESN with no own product", "dealbreakers": ["ESN"], "uncertainty": "low"}
    with patch("anpe.clients.mistral._client") as mock_client:
        mock_client.chat.complete_async = AsyncMock(return_value=_mock_response(data))
        result = await llm_eval(
            summary="Large ESN, 500 employees, staff augmentation only.",
            profile="Looking for small PME, clean product, no ESN.",
        )

    assert result.score == "discard"
    assert result.dealbreakers == ["ESN"]
