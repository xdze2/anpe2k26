"""ANPE CLI."""

from __future__ import annotations

import click
from rich.console import Console

from anpe.engine.run_step import run_step
from anpe.engine.vault import Vault
from anpe.tools.geo_api import search_cities

console = Console()


@click.group()
def cli() -> None:
    """ANPE -- Assistant Numerique Pour l'Emploi."""


cli.add_command(search_cities, name="geo-search")


@cli.command("bootstrap")
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="Re-run even if listing.jsonl exists.",
)
def cmd_bootstrap(overwrite: bool) -> None:
    """Build listing.jsonl from seed_query.yaml."""
    from anpe.steps.bootstrap_step import BootstrapStep

    vault = Vault()
    ran, skipped = run_step(BootstrapStep(), vault, do_max=None, overwrite=overwrite)
    console.print(f"bootstrap: ran={ran} skipped={skipped}")


@cli.command("fetch_siren")
@click.option(
    "--do-max", default=None, type=int, help="Max number of companies to fetch."
)
@click.option(
    "--overwrite", is_flag=True, default=False, help="Re-fetch even if output exists."
)
def cmd_fetch_siren(do_max: int | None, overwrite: bool) -> None:
    """Fetch SIREN registry data for each company in listing.jsonl."""
    from anpe.steps.fetch_siren_step import FetchSirenStep

    vault = Vault()
    ran, skipped = run_step(FetchSirenStep(), vault, do_max=do_max, overwrite=overwrite)
    console.print(f"fetch_siren: ran={ran} skipped={skipped}")


@cli.command("fetch_ddg")
@click.option(
    "--do-max", default=None, type=int, help="Max number of companies to fetch."
)
@click.option(
    "--overwrite", is_flag=True, default=False, help="Re-fetch even if exists."
)
def cmd_fetch_ddg(do_max: int | None, overwrite: bool) -> None:
    """Fetch DuckDuckGo search results for each company with siren data."""
    from anpe.steps.fetch_ddg_step import FetchDdgStep

    vault = Vault()
    ran, skipped = run_step(FetchDdgStep(), vault, do_max=do_max, overwrite=overwrite)
    console.print(f"fetch_ddg: ran={ran} skipped={skipped}")


@cli.command("summarize_ddg")
@click.option(
    "--do-max", default=None, type=int, help="Max number of companies to summarize."
)
@click.option(
    "--overwrite", is_flag=True, default=False, help="Re-summarize even if exists."
)
def cmd_summarize_ddg(do_max: int | None, overwrite: bool) -> None:
    """Summarize DDG results with LLM for each company with DDG data."""
    from anpe.steps.summarize_ddg_step import SummarizeDdgStep

    vault = Vault()
    ran, skipped = run_step(
        SummarizeDdgStep(), vault, do_max=do_max, overwrite=overwrite
    )
    console.print(f"summarize_ddg: ran={ran} skipped={skipped}")


@cli.command("llm_eval")
@click.option(
    "--do-max", default=None, type=int, help="Max number of companies to eval."
)
@click.option(
    "--overwrite", is_flag=True, default=False, help="Re-eval even if output exists."
)
def cmd_llm_eval(do_max: int | None, overwrite: bool) -> None:
    """Score each summarized company against the user profile."""
    from anpe.steps.eval_step import EvalStep

    vault = Vault()
    ran, skipped = run_step(
        EvalStep(),
        vault,
        do_max=do_max,
        overwrite=overwrite,
    )
    console.print(f"llm_eval: ran={ran} skipped={skipped}")


@cli.command("review")
@click.option(
    "--do-max", default=None, type=int, help="Max number of companies to review."
)
@click.option(
    "--random", "random_order", is_flag=True, default=False, help="Shuffle order."
)
@click.option(
    "--overwrite", is_flag=True, default=False, help="Re-review already-reviewed nodes."
)
def cmd_review(
    do_max: int | None,
    random_order: bool,
    overwrite: bool,
) -> None:
    """Interactive terminal review of summarized companies."""
    from anpe.steps.review_step import ReviewStep

    vault = Vault()
    ran, skipped = run_step(
        ReviewStep(),
        vault,
        do_max=do_max,
        overwrite=overwrite,
        random_order=random_order,
    )
    console.print(f"review: ran={ran} skipped={skipped}")


@cli.command("list")
@click.option("--nbr", default=None, type=int, help="Max rows to show.")
@click.option(
    "--sort-field",
    default="node_id",
    type=click.Choice(["node_id", "score", "reaction"]),
    help="Sort field.",
)
@click.option(
    "--state",
    default=None,
    type=click.Choice(["reviewed", "evaled", "summarized", "any"]),
    help="Filter by pipeline stage reached.",
)
@click.option("--export", default=None, type=click.Path(), help="Export to CSV file.")
def cmd_list(
    nbr: int | None,
    sort_field: str,
    state: str | None,
    export: str | None,
) -> None:
    """List all companies in the vault."""
    import json
    import re

    from anpe.engine.vault import Vault

    _HEADCOUNT_BANDS: dict[str, str] = {
        "00": "0",
        "01": "1-2",
        "02": "3-5",
        "03": "6-9",
        "11": "10-19",
        "12": "20-49",
        "21": "50-99",
        "22": "100-199",
        "31": "200-249",
        "32": "250-499",
        "41": "500-999",
        "42": "1000-1999",
        "51": "2000-4999",
        "52": "5000-9999",
        "53": "10000+",
    }

    _SCORE_COLOR = {
        "good": "green",
        "maybe": "yellow",
        "discard": "red",
        "enrich": "blue",
    }

    def _extract_summary_snippet(summary: str) -> str:
        """Extract Type/Marché tags from the first line of the DDG summary."""
        if not summary:
            return ""
        first_line = summary.split("\n")[0]
        # strip bold markers, keep values
        return re.sub(r"\*\*[^*]+\*\*:\s*", "", first_line).strip()

    vault = Vault()
    nodes_dir = vault.root / "nodes"
    if not nodes_dir.exists():
        console.print("[dim]no nodes found.[/]")
        return

    rows = []
    for node_dir in sorted(nodes_dir.iterdir()):
        if not node_dir.is_dir():
            continue
        node_id = node_dir.name

        summary_paths = list(node_dir.glob("summarize_ddg_*.json"))
        if not summary_paths:
            if state not in (None, "any"):
                continue
            rows.append(
                {
                    "node_id": node_id,
                    "name": "",
                    "size": "",
                    "info": "",
                    "reaction": "",
                    "score": "",
                    "fit": "",
                }
            )
            continue

        try:
            sum_data = json.loads(summary_paths[0].read_bytes())
        except Exception:
            sum_data = {}

        if sum_data.get("status") != "ok":
            continue

        siren_paths = list(node_dir.glob("fetch_siren_*.json"))
        siren_data: dict = {}  # type: ignore[type-arg]
        if siren_paths:
            try:
                siren_data = json.loads(siren_paths[0].read_bytes())
            except Exception:
                pass

        eval_paths = list(node_dir.glob("eval_*.json"))
        eval_data: dict = {}  # type: ignore[type-arg]
        if eval_paths:
            try:
                eval_data = json.loads(eval_paths[0].read_bytes())
            except Exception:
                pass

        review_paths = list(node_dir.glob("review_*.json"))
        review_data: dict = {}  # type: ignore[type-arg]
        if review_paths:
            try:
                review_data = json.loads(review_paths[0].read_bytes())
            except Exception:
                pass

        reached = "summarized"
        if eval_data:
            reached = "evaled"
        if review_data:
            reached = "reviewed"

        if state is not None and state != "any" and reached != state:
            continue

        siege = siren_data.get("siege", {})
        nom_legal = siren_data.get("nom_complet", "")
        name = siege.get("nom_commercial") or nom_legal or node_id
        size_code = siren_data.get("tranche_effectif_salarie", "")
        size = _HEADCOUNT_BANDS.get(size_code, size_code) if size_code else ""

        rows.append(
            {
                "node_id": node_id,
                "name": name,
                "size": size,
                "info": _extract_summary_snippet(sum_data.get("summary", "")),
                "reaction": review_data.get("reaction", ""),
                "score": eval_data.get("score", ""),
                "fit": eval_data.get("fit", ""),
            }
        )

    if sort_field == "score":
        _order = {"good": 0, "maybe": 1, "enrich": 2, "discard": 3, "": 4}
        rows.sort(key=lambda r: _order.get(r["score"], 4))
    elif sort_field == "reaction":
        rows.sort(key=lambda r: r["reaction"])
    else:
        rows.sort(key=lambda r: r["node_id"])

    if nbr is not None:
        rows = rows[:nbr]

    if export:
        import csv

        path = export
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "node_id",
                    "name",
                    "size",
                    "info",
                    "reaction",
                    "score",
                    "fit",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        console.print(f"[dim]exported {len(rows)} row(s) to {path}[/]")
        return

    for row in rows:
        score = row["score"]
        reaction = row["reaction"]
        color = _SCORE_COLOR.get(score, "")
        score_tag = f"[{color}]{score}[/]" if color else score

        name_part = (
            f"[bold]{row['name']}[/]" if row["name"] else f"[dim]{row['node_id']}[/]"
        )
        size_part = f"  [dim]{row['size']}[/]" if row["size"] else ""
        reaction_part = f"  [cyan]{reaction}[/]" if reaction else ""
        info_part = f"  [dim]{row['info']}[/]" if row["info"] else ""

        console.print(f"--- {name_part}{size_part}{reaction_part}{info_part}")
        console.print(f"        {score_tag}  {row['fit']}")

    console.print(f"\n[dim]{len(rows)} node(s)[/]")


@cli.command("web")
@click.option("--port", default=5000, type=int, help="Port to listen on.")
@click.option("--debug", is_flag=True, default=False)
def cmd_web(port: int, debug: bool) -> None:
    """Start the web UI."""
    from anpe.web import app

    app.run(port=port, debug=debug)


@cli.command("view")
@click.argument("node_id")
def cmd_view(node_id: str) -> None:
    """Print a formatted markdown summary for a company."""
    from rich.markdown import Markdown

    from anpe.engine.vault import Vault
    from anpe.steps.view import node_view

    vault = Vault()
    nodes_dir = vault.root / "nodes"
    node_dir = nodes_dir / node_id

    if not node_dir.exists():
        console.print(f"[red]node not found:[/] {node_id}")
        raise SystemExit(1)

    summary_paths = list(node_dir.glob("summarize_ddg_*.json"))
    if not summary_paths:
        console.print(f"[yellow]no summary found for[/] {node_id}")
        raise SystemExit(1)

    summary_uri = str(summary_paths[0].relative_to(vault.root))

    siren_uri: str | None = None
    siren_paths = list(node_dir.glob("fetch_siren_*.json"))
    if siren_paths:
        siren_uri = str(siren_paths[0].relative_to(vault.root))

    eval_uri: str | None = None
    eval_paths = list(node_dir.glob("eval_*.json"))
    if eval_paths:
        eval_uri = str(eval_paths[0].relative_to(vault.root))

    md = node_view(vault, summary_uri, siren_uri=siren_uri, eval_uri=eval_uri)
    console.print(Markdown(md))
