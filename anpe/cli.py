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
def cmd_fetch_siren() -> None:
    """[stub] Fetch SIREN data for each company in listing.jsonl."""
    raise NotImplementedError("step 5")


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
