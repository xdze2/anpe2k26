#!/usr/bin/env python3
"""Get postal codes for communes within a radius of a city.

API doc: tools/siren_infos/geo_api_gouv_definition.yml
"""
import json
import math
import click
import requests
import yaml
from pathlib import Path

GEO_API_URL = "https://geo.api.gouv.fr"
OUTPUT_DIR = (
    Path(__file__).parent.parent / "data" / "company_data" / "postcode_searches"
)
CACHE_DIR = OUTPUT_DIR


def geocode_city(city: str) -> tuple[float, float, dict]:
    """City name → (lat, lon, commune_dict) via geo.api.gouv.fr."""
    resp = requests.get(
        f"{GEO_API_URL}/communes",
        params={
            "nom": city,
            "boost": "population",
            "fields": "centre,codeDepartement,codesPostaux,population",
            "limit": 1,
        },
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise click.ClickException(f"City not found: {city!r}")
    r = results[0]
    lon, lat = r["centre"]["coordinates"]
    return lat, lon, r


def get_departement_at(lat: float, lon: float) -> str:
    """lat/lon → codeDepartement of the commune at that point."""
    resp = requests.get(
        f"{GEO_API_URL}/communes",
        params={"lat": lat, "lon": lon, "fields": "codeDepartement"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise click.ClickException(f"No commune found at ({lat}, {lon})")
    return results[0]["codeDepartement"]


def bounding_box_corners(
    lat: float, lon: float, radius_km: float
) -> list[tuple[float, float]]:
    """Return the 4 corners of the bounding box around a point."""
    dlat = math.degrees(radius_km / 6371)
    dlon = math.degrees(radius_km / (6371 * math.cos(math.radians(lat))))
    return [
        (lat + dlat, lon - dlon),
        (lat + dlat, lon + dlon),
        (lat - dlat, lon - dlon),
        (lat - dlat, lon + dlon),
    ]


def get_departements_for_radius(
    lat: float, lon: float, radius_km: float, center_dep: str
) -> list[str]:
    """Return unique department codes covering the bounding box of the search circle."""
    corners = bounding_box_corners(lat, lon, radius_km)
    codes = {get_departement_at(c_lat, c_lon) for c_lat, c_lon in corners}
    codes.add(center_dep)
    return sorted(codes)


def get_communes_for_departement(code_dep: str) -> list[dict]:
    """Download all communes for a department, with file cache."""
    cache_file = CACHE_DIR / f"communes_for_departement_{code_dep}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    resp = requests.get(
        f"{GEO_API_URL}/departements/{code_dep}/communes",
        params={"fields": "nom,codesPostaux,centre,population"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def filter_communes_by_distance(
    communes: list[dict], lat: float, lon: float, radius_km: float
) -> list[dict]:
    result = []
    for c in communes:
        centre = c.get("centre")
        if not centre:
            continue
        c_lon, c_lat = centre["coordinates"]
        if haversine_km(lat, lon, c_lat, c_lon) <= radius_km:
            result.append(c)
    return result


@click.command()
@click.argument("city")
@click.option("--radius", "-r", default=10, show_default=True, help="Radius in km")
def search_cities(city: str, radius: int):
    """Find postal codes within RADIUS km of CITY and save to a YAML file."""
    click.echo(f"Geocoding {city!r}...")
    lat, lon, center_commune = geocode_city(city)
    center_dep = center_commune["codeDepartement"]
    click.echo(f"  → {lat:.4f}, {lon:.4f} (dept {center_dep})")

    click.echo("Resolving departments covering the search area...")
    dep_codes = get_departements_for_radius(lat, lon, radius, center_dep)
    click.echo(f"  → departments: {', '.join(dep_codes)}")

    all_communes: list[dict] = []
    for dep in dep_codes:
        cache_file = CACHE_DIR / f"communes_for_departement_{dep}.json"
        communes = get_communes_for_departement(dep)
        source = "cached" if cache_file.exists() else "downloaded"
        click.echo(f"  → {dep}: {len(communes)} communes ({source})")
        all_communes.extend(communes)

    # Deduplicate by INSEE code (communes appear once per department fetch)
    seen: set[str] = set()
    unique_communes = []
    for c in all_communes:
        code = c.get("code", "")
        if code not in seen:
            seen.add(code)
            unique_communes.append(c)

    nearby = filter_communes_by_distance(unique_communes, lat, lon, radius)
    click.echo(f"  → {len(nearby)} communes within {radius} km")

    # Build sorted list of (postal_code, commune_name, population) — one row per postal code
    rows = []
    for commune in nearby:
        name = commune.get("nom", "")
        pop = commune.get("population")
        for code in commune.get("codesPostaux", []):
            rows.append({"postal_code": code, "name": name, "population": pop})
    rows.sort(key=lambda r: r["postal_code"])

    entry = {
        "city": city,
        "city_population": center_commune.get("population"),
        "city_postal_codes": center_commune.get("codesPostaux", []),
        "radius_km": radius,
        "lat": lat,
        "lon": lon,
        "commune_count": len(nearby),
        "communes": rows,
    }

    slug = f"{city.lower().replace(' ', '_')}_{radius}km"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"{slug}.yaml"

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(entry, f, allow_unicode=True, sort_keys=False)

    click.echo(f"✓ {len(rows)} entries saved to {output_file}")
    for row in rows[:5]:
        click.echo(f"  {row['postal_code']}  {row['name']}  (pop: {row['population']})")
    if len(rows) > 5:
        click.echo("  ...")


if __name__ == "__main__":
    search_cities()
