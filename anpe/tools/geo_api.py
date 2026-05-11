"""Search cities by name via geo.api.gouv.fr."""

import click
import httpx

GEO_API_URL = "https://geo.api.gouv.fr"


@click.command()
@click.argument("city")
def search_cities(city: str) -> None:
    """Search for a city by name and print the top matches."""
    resp = httpx.get(
        f"{GEO_API_URL}/communes",
        params={
            "nom": city,
            "boost": "population",
            "fields": "centre,codeDepartement,codesPostaux,population",
            "limit": 5,
        },
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise click.ClickException(f"No city found for {city!r}")

    for r in results:
        lon, lat = r["centre"]["coordinates"]
        dep = r.get("codeDepartement", "?")
        pop = r.get("population", "?")
        click.echo(f"  # {r['nom']} (pop {pop})")
        click.echo(f'  - city: "{r["nom"]}"')
        click.echo(f"    lat: {lat:.2f}")
        click.echo(f"    lon: {lon:.2f}")
        click.echo(f'    radius_km: 30')
        click.echo(f'    departements: ["{dep}"]')
        click.echo()


if __name__ == "__main__":
    search_cities()
