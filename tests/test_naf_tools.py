import pytest
from pydantic_ai.models.test import TestModel

from anpe.agent import agent
from anpe.tools.naf import _load_categories, _load_csv_index


def test_csv_index_loads():
    index = _load_csv_index()
    assert "71.12B" in index
    assert "Ingénierie" in index["71.12B"]


def test_categories_load():
    cats = _load_categories()
    assert "engineering" in cats
    assert "core-tech" in cats


def test_naf_lookup_known_code():
    index = _load_csv_index()
    # engineering code from categories
    assert "71.12B" in index


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


def test_naf_search_scores_engineering():
    from anpe.tools.naf import _load_categories

    categories = _load_categories()
    kw_lower = "engineering"
    scored = []
    for cat_name, cat in categories.items():
        score = 0
        searchable = (cat_name + " " + cat["description"]).lower()
        for word in kw_lower.split():
            if len(word) > 2 and word in searchable:
                score += 2
        scored.append((score, cat_name))
    scored.sort(key=lambda x: -x[0])
    assert scored[0][1] == "engineering"
