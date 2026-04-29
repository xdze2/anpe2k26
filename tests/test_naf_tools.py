import pytest
from pydantic_ai.models.test import TestModel

from anpe.agent import agent
from anpe.tools.naf import _load_csv_index


def test_csv_index_loads():
    index = _load_csv_index()
    assert "71.12B" in index
    assert "Ingénierie" in index["71.12B"]


def test_naf_lookup_unknown_code():
    index = _load_csv_index()
    assert "99.99Z" not in index


@pytest.mark.asyncio
async def test_naf_lookup_tool_called():
    with agent.override(model=TestModel(custom_output_text="Code trouvé.")):
        result = await agent.run("Que signifie le code NAF 71.12B ?")
    assert result.output is not None


@pytest.mark.asyncio
async def test_naf_search_tool_called():
    with agent.override(model=TestModel(custom_output_text="Voici les codes NAF.")):
        result = await agent.run("Trouve des entreprises en ingénierie et IA.")
    assert result.output is not None


def test_naf_search_returns_matches():
    from anpe.tools.naf import _load_csv_index

    index = _load_csv_index()
    words = ["ingénierie"]
    scored = [
        (sum(1 for w in words if w in label.lower()), code, label)
        for code, label in index.items()
    ]
    scored = [(s, c, l) for s, c, l in scored if s > 0]
    assert any("71.12B" == code for _, code, _ in scored)
