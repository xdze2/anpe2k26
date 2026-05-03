"""Distance and size filtering for bootstrap etablissement results."""

from __future__ import annotations

import math


HEADCOUNT_BANDS: dict[str, str] = {
    "00": "0", "01": "1-2", "02": "3-5", "03": "6-9",
    "11": "10-19", "12": "20-49", "21": "50-99",
    "22": "100-199", "31": "200-249", "32": "250-499",
    "41": "500-999", "42": "1 000-1 999", "51": "2 000-4 999",
    "52": "5 000-9 999", "53": "10 000+",
}

# Ordered list of tranche codes for range comparison.
_TRANCHE_ORDER: list[str] = list(HEADCOUNT_BANDS.keys())


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def within_radius(
    etab_lat: float,
    etab_lon: float,
    center_lat: float,
    center_lon: float,
    radius_km: float,
) -> float | None:
    """Return distance in km if within radius, else None."""
    d = haversine_km(center_lat, center_lon, etab_lat, etab_lon)
    return d if d <= radius_km else None


def tranche_in_range(tranche: str, tranche_min: str, tranche_max: str) -> bool:
    """Return True if tranche code is within [tranche_min, tranche_max] inclusive."""
    if not tranche:
        return False
    return tranche_min <= tranche <= tranche_max
