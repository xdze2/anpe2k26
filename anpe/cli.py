"""ANPE CLI — interactive chat + prospect commands."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.text import Text

from anpe.node_dir import NodeDir

if TYPE_CHECKING:
    from anpe.prospect.pipeline import StepLog

console = Console()

_QUIT_WORDS = {"quit", "exit", "q", "quitter", "au revoir", "bye"}


# ---------------------------------------------------------------------------
# Chat helpers
# ---------------------------------------------------------------------------


def _print_header() -> None:
    console.print()
    console.print(" [bold cyan]ANPE[/] — Assistant Numérique Pour l'Emploi")
    console.print(" [dim]tapez 'quitter' pour quitter[/]")
    console.print()


def _print_assistant(text: str) -> None:
    console.print(f" [bold cyan]ANPE[/]  {text}")
    console.print()


async def _chat_loop() -> None:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML
    from pydantic_ai import AgentStreamEvent, FunctionToolCallEvent, RunContext
    from rich.columns import Columns
    from rich.console import Group
    from rich.live import Live
    from rich.spinner import Spinner

    from anpe.agent import agent
    from anpe.config import settings

    def _print_status(tokens_in: int, tokens_out: int) -> None:
        parts = Text()
        parts.append(f" {tokens_in} → {tokens_out} tokens", style="dim")
        parts.append("   ", style="dim")
        parts.append(settings.openrouter_model, style="dim")
        console.print(parts)
        console.print()

    async def _run_agent(user_text: str) -> tuple[str, int, int]:
        tool_lines: list[Text] = []
        spinner = Spinner("dots", style="yellow")

        def _renderable() -> Group:
            spinner_line = Columns([spinner, Text("  en attente…", style="dim")])
            return Group(spinner_line, *tool_lines)

        live = Live(_renderable(), console=console, transient=True, refresh_per_second=12)

        async def _handle_events(
            ctx: RunContext[None], events: AsyncIterable[AgentStreamEvent]
        ) -> None:
            async for event in events:
                if isinstance(event, FunctionToolCallEvent):
                    tool_lines.append(Text(f"   ⟳ {event.part.tool_name}", style="yellow"))
                    live.update(_renderable())

        with live:
            result = await agent.run(user_text, event_stream_handler=_handle_events)

        usage = result.usage()
        return result.output, usage.input_tokens or 0, usage.output_tokens or 0

    _print_header()
    _print_assistant("Bonjour ! Comment puis-je vous aider ?")

    session: PromptSession[str] = PromptSession()
    prompt = HTML("<ansigreen><b> ❯</b></ansigreen> ")

    while True:
        try:
            user_input = (await session.prompt_async(prompt)).strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in _QUIT_WORDS:
            break

        console.print()
        try:
            output, tokens_in, tokens_out = await _run_agent(user_input)
            _print_assistant(output)
            _print_status(tokens_in, tokens_out)
        except Exception as e:
            console.print(f" [bold red]Erreur[/] {e}")
            console.print()


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """ANPE — Assistant Numérique Pour l'Emploi."""


@cli.command("chat")
def chat() -> None:
    """Start the interactive chat."""
    asyncio.run(_chat_loop())


# ---------------------------------------------------------------------------
# Prospect group
# ---------------------------------------------------------------------------


@cli.group("prospect")
def prospect_group() -> None:
    """Research and enrich prospected companies."""


def _print_step_log(log: StepLog) -> None:
    status_style = {
        "ok": "green",
        "not_relevant": "red",
        "no_data": "yellow",
        "fetch_error": "red",
        "summarize_error": "red",
        "empty_queue": "dim",
    }.get(log.status, "white")

    console.print(f" [dim]node[/]   [bold]{log.node_id}[/]")
    if log.tool:
        console.print(f" [dim]fetched[/] [{log.tool}] {log.target}")
    console.print(f" [dim]status[/] [{status_style}]{log.status}[/]")
    for tool, target in log.new_targets:
        console.print(f" [dim]queued[/] [{tool}] {target}")


@prospect_group.command("seed")
@click.option("--count", default=10, show_default=True, help="Number of new nodes to create.")
def prospect_seed(count: int) -> None:
    """Pick N new companies from the listing and create prospect nodes.

    Reads user_data/company_listing.csv, skips companies that already have a
    node, and creates up to COUNT new nodes each with an initial DDG target.

    Example: anpe prospect seed --count 5
    """
    from anpe.node_dir import USER_DATA_DIR
    from anpe.prospect.seed import seed_from_listing

    csv_path = USER_DATA_DIR / "company_listing.csv"
    if not csv_path.exists():
        console.print(f" [bold red]Error[/] listing not found: {csv_path}")
        return

    created = seed_from_listing(csv_path, count)

    if not created:
        console.print(" [dim]No new companies to seed (all already have nodes, or listing is empty).[/]")
        return

    for node_id in created:
        console.print(f" [green]created[/] [bold]{node_id}[/]")
    console.print(f"\n [dim]{len(created)} node(s) created.[/]")


@prospect_group.command("run")
@click.argument("node_ids", nargs=-1, metavar="[NODE_ID]...")
@click.option("-n", "budget", default=1, show_default=True,
              help="Total step budget across all nodes.")
@click.option("--all-nodes", is_flag=True, help="Run on all existing nodes.")
@click.option("--until-done", is_flag=True,
              help="Run until all queues empty (ignores -n). Use with caution.")
def prospect_run(
    node_ids: tuple[str, ...], budget: int, all_nodes: bool, until_done: bool
) -> None:
    """Run the prospect pipeline on nodes (depth-first, total step budget).

    Examples:
      anpe prospect run chapsvision_851035329          # 1 step (default)
      anpe prospect run -n 10                          # 10 steps, all nodes
      anpe prospect run -n 5 chapsvision_851035329 incomm_479144438
      anpe prospect run --all-nodes -n 10
      anpe prospect run --all-nodes --until-done
    """
    from anpe.prospect.pipeline import _all_node_ids_by_ctime, run_batch

    if node_ids and all_nodes:
        raise click.UsageError("NODE_IDs and --all-nodes are mutually exclusive.")
    if until_done and budget != 1:
        raise click.UsageError("-n and --until-done are mutually exclusive.")

    if all_nodes:
        ids = _all_node_ids_by_ctime()
    elif node_ids:
        ids = list(node_ids)
    else:
        ids = _all_node_ids_by_ctime()

    if not ids:
        console.print(" [dim]No nodes found.[/]")
        return

    missing = [nid for nid in ids if not NodeDir(nid).exists()]
    if missing:
        for nid in missing:
            console.print(f" [bold red]Error[/] node {nid!r} not found")
        return

    effective_budget = None if until_done else budget

    async def _run() -> None:
        async for log in run_batch(ids, effective_budget):
            _print_step_log(log)
            if log.status == "blocked":
                console.print(" [bold red]blocked[/] — stopping run")

    asyncio.run(_run())


@prospect_group.command("add_target")
@click.argument("node_id")
@click.argument("tool")
@click.argument("keyword")
def add_target(node_id: str, tool: str, keyword: str) -> None:
    """Append a fetch target to a node's queue.

    Example: anpe prospect add_target acme ddg "Acme Corp France"
    """
    from anpe.prospect.registry import FETCH_TOOLS

    if tool not in FETCH_TOOLS:
        raise click.BadParameter(
            f"must be one of {list(FETCH_TOOLS)}", param_hint="TOOL"
        )
    node = NodeDir(node_id)
    if not node.exists():
        console.print(f" [bold red]Error[/] node {node_id!r} not found — use 'prospect seed' to create nodes")
        return
    node.append_target(tool, keyword)
    console.print(f" [dim]node[/] [bold]{node_id}[/]")
    console.print(f" [dim]queued[/] [{tool}] {keyword}")


@prospect_group.command("step")
@click.argument("node_id")
def prospect_step(node_id: str) -> None:
    """Run one prospect step on a node (fetch if pending, summarize if fetch_done).

    Example: anpe prospect step acme
    """
    from anpe.prospect.pipeline import enrich_step

    log = asyncio.run(enrich_step(node_id))
    _print_step_log(log)


@prospect_group.command("status")
@click.argument("node_id")
def prospect_status(node_id: str) -> None:
    """Show fetch status and history for a node.

    Example: anpe prospect status acme
    """
    node = NodeDir(node_id)
    if not node.exists():
        console.print(f" [bold red]Error[/] node {node_id!r} not found")
        return

    rows = node.get_fetch_history()
    if not rows:
        console.print(f" [dim]node[/] [bold]{node_id}[/]  [dim](no fetch history)[/]")
        return

    console.print(f" [dim]node[/] [bold]{node_id}[/]")
    console.print()

    _STATUS_STYLE = {
        "put": "yellow",
        "fetch_done": "cyan",
        "fetch_error": "red",
        "not_found": "red",
        "retryable": "yellow",
        "blocked": "red",
        "summarize_done": "green",
        "summarize_error": "red",
    }

    for row in rows:
        style = _STATUS_STYLE.get(row["last_event"], "white")
        target_display = row["target"][:50]
        ts = row["put_ts"][:16].replace("T", " ") if row["put_ts"] else ""
        console.print(
            f" [dim]{row['uid']}[/]  [bold]{row['tool']}[/]  {target_display}"
            f"  [{style}]{row['last_event']}[/]  [dim]{ts}[/]"
        )


@prospect_group.command("summarize")
@click.argument("node_id")
@click.argument("fetch_uid", required=False, default=None)
def prospect_summarize(node_id: str, fetch_uid: str | None) -> None:
    """Re-run summarize on an already-fetched target, bypassing the queue.

    Uses the most recent fetch_done target if FETCH_UID is omitted.
    Intended for prompt tuning — does not re-fetch.

    Examples:
      anpe prospect summarize acme
      anpe prospect summarize acme a3f1
    """
    from anpe.prospect.pipeline import summarize_step

    try:
        log = asyncio.run(summarize_step(node_id, fetch_uid))
    except ValueError as e:
        console.print(f" [bold red]Error[/] {e}")
        return
    _print_step_log(log)


@cli.group("bootstrap")
def bootstrap_group() -> None:
    """Generate company listing from SIRENE API."""


@bootstrap_group.command("run")
@click.option("--refresh", is_flag=True, default=False, help="Invalidate cache and re-fetch all pairs.")
def bootstrap_run(refresh: bool) -> None:
    """Build user_data/company_listing.csv from user_profile.yaml.

    Reads user_data/user_profile.yaml from the project root.
    Writes output to user_data/company_listing.csv.
    Re-running is safe — cache is reused unless --refresh is passed.
    """
    import logging
    from pathlib import Path

    from anpe.bootstrap.pipeline import run as bootstrap_pipeline

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    root = Path.cwd()
    profile_path = root / "user_data" / "user_profile.yaml"
    output_path = root / "user_data" / "company_listing.csv"
    cache_dir = root / "cache_data" / "bootstrap_cache"

    if not profile_path.exists():
        raise click.ClickException(f"user_profile.yaml not found at {profile_path}")

    console.print(f" [dim]profile[/] {profile_path}")
    console.print(f" [dim]output[/]  {output_path}")
    if refresh:
        console.print(" [yellow]--refresh: cache will be invalidated[/]")

    count = bootstrap_pipeline(profile_path, output_path, cache_dir, refresh=refresh)
    console.print(f" [bold green]✓[/] {count} companies written to {output_path}")


def run() -> None:
    cli()
