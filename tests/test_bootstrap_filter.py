"""Tests for anpe/bootstrap/filter.py — pure distance and size filtering."""

import pytest
from anpe.steps.bootstrap.filter import haversine_km, within_radius, tranche_in_range


def test_haversine_known_distance():
    # Toulouse to Paris is roughly 590 km
    d = haversine_km(43.60, 1.44, 48.85, 2.35)
    assert 580 < d < 600


def test_haversine_zero():
    assert haversine_km(43.6, 1.44, 43.6, 1.44) == pytest.approx(0.0)


def test_within_radius_inside():
    # Point 5 km away, radius 10 km → should return a float
    d = within_radius(43.65, 1.44, 43.60, 1.44, 10.0)
    assert d is not None
    assert d < 10.0


def test_within_radius_outside():
    # Paris is ~590 km from Toulouse, radius 30 km → None
    d = within_radius(48.85, 2.35, 43.60, 1.44, 30.0)
    assert d is None


def test_tranche_in_range_inside():
    assert tranche_in_range("21", "11", "41") is True


def test_tranche_in_range_boundary():
    assert tranche_in_range("11", "11", "41") is True
    assert tranche_in_range("41", "11", "41") is True


def test_tranche_in_range_outside():
    assert tranche_in_range("03", "11", "41") is False
    assert tranche_in_range("42", "11", "41") is False


def test_tranche_in_range_empty():
    assert tranche_in_range("", "11", "41") is False
