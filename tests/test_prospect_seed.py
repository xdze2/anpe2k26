"""Tests for anpe/prospect/seed.py."""

from anpe.prospect.seed import slugify, node_id_for


def test_slugify_basic():
    assert slugify("CHAPSVISION") == "chapsvision"


def test_slugify_accents():
    assert slugify("SOCIÉTÉ GÉNÉRALE") == "societe_generale"


def test_slugify_punctuation():
    assert slugify("A & B (France)") == "a_b_france"


def test_node_id_for():
    assert node_id_for("CHAPSVISION", "851035329") == "chapsvision_851035329"
