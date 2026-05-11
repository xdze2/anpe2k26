"""ANPE CLI."""

from __future__ import annotations

import asyncio
import itertools
import json
import sys

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.padding import Padding
from rich.rule import Rule
from rich.text import Text

from anpe.node_dir import NodeDir

console = Console()

USER_VAULT = "USER_VAULT"

# Each scripts:
# - skip if the output exist (unless overwrite=True)
# - skip if missing input
# - Do max do_max iterations
# - (optional) store input files date, check for new file (makefile like)
# - API results are cached at low level, dir cache_data


@click.group()
def cli() -> None:
    """ANPE -- Assistant Numerique Pour l'Emploi."""


@cli.command("bootstrap")
def cmd_bootstrap() -> None:
    """
    Input: user_vault/seed_query.yaml.
    Output: a list of candidates companies in user_vault/listing.jsonl

    External input:
    - Geo Api
    - RechercheEntreprise API (Siren)

    Search company by distance and Naf code, (siret and siren),

    company commercial name
    naf label and code
    """
    ...


@cli.command("fetch_siren")
def cmd_siren(do_max: int = 10, overwrite: bool = False) -> None:
    """Fetch the whole siren data, (aka more detailled than the listing)

    input: USER_VAULT/listing.jsonl, do_max
    output: USER_VAULT/nodes/<id>/siren_<id>.json

    id={siren}_{slug}

    External input:
    - RechercheEntreprise API (Siren)

    Output fields:
    company CA, director name, ...
    """
    ...


@cli.command("fetch_ddg")
def cmd_fetch_ddg(do_max: int = 10, overwrite: bool = False) -> None:
    """
    input: USER_VAULT/nodes/<id>/siren_<id>.json
    output: USER_VAULT/nodes/<id>/ddg_search_<id>.json

    Search the Company name on DuckDuckGo

    """
    ...


@cli.command("summarize_ddg")
def cmd_summarize_ddg(do_max: int = 10, overwrite: bool = False) -> None:
    """Call LLM to extract info from the ddg search

    input files:
    - USER_VAULT/nodes/<id>/ddg_search_<id>.json
    - USER_VAULT/nodes/<id>/siren_<id>.json
    output files:
    - USER_VAULT/nodes/<id>/ddg_summarize_<id>.json

    External input:
    - Mistral LLM Call

    Methods and consts
    - system prompt, user prompt
    - ddg_company_summary(siren_data) -> markdown

    Output fields:
    - status: str (ok, not_releveant, ...)
    - summary: markdown
    - next_targets: ...
    - model: model_name
    - code_version: str
    - prompt: str
    """
    ...


@cli.command("review")
def cmd_review(
    do_max: int = 10, overwrite: bool = False, skip_non_relevant: bool = True
) -> None:
    """User review (user input)
    inputs:
    - USER_VAULT/nodes/<id>/siren_<id>.json
    - USER_VAULT/nodes/<id>/ddg_summarize_<id>.json
    output:
    - USER_VAULT/nodes/<id>/user_review_<id>.json

    External input:
    - user: skip, quit, multiple choice input

    Methods:
    - user_company_summary(id) -> markdown

    Output fields:
    - reaction: str ("interested", ...)
    - reason: str (optional)
    """
    ...


@cli.command("llm_eval")
def cmd_eval(overwrite: bool = False, skip_non_relevant: bool = True) -> None:
    """LLM eval
    inputs:
    - USER_VAULT/nodes/<id>/siren_<id>.json
    - USER_VAULT/nodes/<id>/ddg_summarize_<id>.json
    - USER_VAULT/user_preference.md
    output:
    - USER_VAULT/nodes/<id>/llm_eval_<id>.json

    External input:
    - LLM call

    Output fields:
    - score: str
    - fit: str (optional)
    - dealbreakers
    - uncertainty
    - prompt
    """
    ...


@cli.command("list")
def cmd_eval(
    skip_non_relevant: bool = True,
    nbr: int = None,
    sort_field: str = None,
    state: str = None,
) -> None:
    """print a formatted list of companies."""


@cli.command("view")
def cmd_view(node_id: str) -> None:
    """Print a formatted summary for a company."""
