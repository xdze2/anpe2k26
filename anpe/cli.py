"""ANPE CLI."""

from __future__ import annotations

import click
from rich.console import Console

from anpe.engine.run_step import run_step
from anpe.engine.vault import Vault

console = Console()


@click.group()
def cli() -> None:
    """ANPE -- Assistant Numerique Pour l'Emploi."""


@cli.command("bootstrap")
@click.option("--overwrite", is_flag=True, default=False, help="Re-run even if listing.jsonl exists.")
def cmd_bootstrap(overwrite: bool) -> None:
    """Build listing.jsonl from seed_query.yaml."""
    from anpe.steps.bootstrap_step import BootstrapStep

    vault = Vault()
    ran, skipped = run_step(BootstrapStep(), vault, do_max=None, overwrite=overwrite)
    console.print(f"bootstrap: ran={ran} skipped={skipped}")


@cli.command("fetch_siren")
@click.option("--do-max", default=None, type=int, help="Max number of companies to fetch.")
@click.option("--overwrite", is_flag=True, default=False, help="Re-fetch even if output exists.")
def cmd_fetch_siren(do_max: int | None, overwrite: bool) -> None:
    """Fetch SIREN registry data for each company in listing.jsonl."""
    from anpe.steps.fetch_siren_step import FetchSirenStep

    vault = Vault()
    ran, skipped = run_step(FetchSirenStep(), vault, do_max=do_max, overwrite=overwrite)
    console.print(f"fetch_siren: ran={ran} skipped={skipped}")


@cli.command("fetch_ddg")
def cmd_fetch_ddg() -> None:
    """[stub] Fetch DuckDuckGo search results per company."""
    raise NotImplementedError("step 6")


@cli.command("summarize_ddg")
def cmd_summarize_ddg() -> None:
    """[stub] Summarize DDG results with LLM."""
    raise NotImplementedError("step 7")


@cli.command("llm_eval")
def cmd_llm_eval() -> None:
    """[stub] LLM evaluation of each company."""
    raise NotImplementedError("step 8")


@cli.command("review")
def cmd_review() -> None:
    """[stub] Interactive user review."""
    raise NotImplementedError("step 9")


@cli.command("list")
def cmd_list() -> None:
    """[stub] Print a formatted list of companies."""
    raise NotImplementedError("step 10")


@cli.command("view")
@click.argument("node_id")
def cmd_view(node_id: str) -> None:
    """[stub] Print a formatted summary for a company."""
    raise NotImplementedError("step 10")
