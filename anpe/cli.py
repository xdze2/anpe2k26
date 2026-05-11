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
@click.option(
    "--keep-non-relevant",
    is_flag=True,
    default=False,
    help="Also eval nodes with status=not_relevant (skipped by default).",
)
def cmd_llm_eval(
    do_max: int | None, overwrite: bool, keep_non_relevant: bool = False
) -> None:
    """Score each summarized company against the user profile."""
    from anpe.steps.eval_step import EvalStep

    vault = Vault()
    ran, skipped = run_step(
        EvalStep(),
        vault,
        do_max=do_max,
        overwrite=overwrite,
        keep_non_relevant=keep_non_relevant,
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
    "--keep-non-relevant",
    is_flag=True,
    default=False,
    help="Also review nodes with status=not_relevant (skipped by default).",
)
@click.option(
    "--overwrite", is_flag=True, default=False, help="Re-review already-reviewed nodes."
)
def cmd_review(
    do_max: int | None,
    random_order: bool,
    keep_non_relevant: bool,
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
        keep_non_relevant=keep_non_relevant,
        random_order=random_order,
    )
    console.print(f"review: ran={ran} skipped={skipped}")


@cli.command("list")
def cmd_list() -> None:
    """[stub] Print a formatted list of companies."""
    raise NotImplementedError("step 10")


@cli.command("view")
@click.argument("node_id")
def cmd_view(node_id: str) -> None:
    """[stub] Print a formatted summary for a company."""
    raise NotImplementedError("step 10")
