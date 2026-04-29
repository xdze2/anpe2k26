import pytest
from pydantic_ai.models.test import TestModel

from anpe.agent import agent


@pytest.mark.asyncio
async def test_agent_returns_response() -> None:
    with agent.override(model=TestModel()):
        result = await agent.run("Bonjour")
    assert result.output is not None
    assert isinstance(result.output, str)


@pytest.mark.asyncio
async def test_agent_handles_empty_like_input() -> None:
    with agent.override(model=TestModel()):
        result = await agent.run("?")
    assert result.output is not None
