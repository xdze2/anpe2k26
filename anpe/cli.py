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
def cmd_llm_eval(
    do_max: int | None, overwrite: bool
) -> None:
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
    help="Sort column.",
)
@click.option(
    "--state",
    default=None,
    type=click.Choice(["reviewed", "evaled", "summarized", "any"]),
    help="Filter by pipeline stage reached.",
)
def cmd_list(
    nbr: int | None,
    sort_field: str,
    state: str | None,
) -> None:
    """Print a formatted table of all companies in the vault."""
    import json

    from rich.table import Table

    from anpe.engine.vault import Vault

    vault = Vault()
    nodes_dir = vault.root / "nodes"
    if not nodes_dir.exists():
        console.print("[dim]no nodes found.[/]")
        return

    _SCORE_COLOR = {
        "good": "green",
        "maybe": "yellow",
        "discard": "red",
        "enrich": "blue",
    }

    rows = []
    for node_dir in sorted(nodes_dir.iterdir()):
        if not node_dir.is_dir():
            continue
        node_id = node_dir.name

        summary_paths = list(node_dir.glob("summarize_ddg_*.json"))
        if not summary_paths:
            if state not in (None, "any"):
                continue
            rows.append({"node_id": node_id, "score": "", "reaction": "", "fit": ""})
            continue

        summary_path = summary_paths[0]
        try:
            sum_data = json.loads(summary_path.read_bytes())
        except Exception:
            sum_data = {}

        if sum_data.get("status") != "ok":
            continue

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

        rows.append(
            {
                "node_id": node_id,
                "score": eval_data.get("score", ""),
                "reaction": review_data.get("reaction", ""),
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

    table = Table(show_header=True, header_style="bold")
    table.add_column("node_id", style="dim")
    table.add_column("score", width=8)
    table.add_column("reaction", width=14)
    table.add_column("fit")

    for row in rows:
        score = row["score"]
        color = _SCORE_COLOR.get(score, "")
        score_cell = f"[{color}]{score}[/]" if color else score
        table.add_row(row["node_id"], score_cell, row["reaction"], row["fit"])

    console.print(table)
    console.print(f"[dim]{len(rows)} node(s)[/]")


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
