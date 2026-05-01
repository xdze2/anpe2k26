"""ANPE CLI — interactive chat + enrichment commands."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from pydantic_ai import AgentStreamEvent, FunctionToolCallEvent, RunContext
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from anpe.agent import agent
from anpe.config import settings
from anpe.enrich.pipeline import enrich_step
from anpe.enrich.registry import FETCH_TOOLS
from anpe.node_dir import NodeDir

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


async def _chat_loop() -> None:
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


@cli.command("add_target")
@click.argument("node_id")
@click.argument("tool", type=click.Choice(list(FETCH_TOOLS)))
@click.argument("keyword")
def add_target(node_id: str, tool: str, keyword: str) -> None:
    """Append a fetch target to a node's queue.

    Example: anpe add_target acme ddg "Acme Corp France"
    """
    node = NodeDir(node_id)
    is_new = not node.exists()
    node.append_target(tool, keyword)
    created = " [dim](created)[/]" if is_new else ""
    console.print(f" [dim]node[/] [bold]{node_id}[/]{created}")
    console.print(f" [dim]queued[/] [{tool}] {keyword}")


@cli.command("enrich")
@click.argument("node_id")
def enrich(node_id: str) -> None:
    """Run one enrichment step on a node.

    Example: anpe enrich acme
    """
    log = asyncio.run(enrich_step(node_id))

    status_style = {
        "ok": "green",
        "not_relevant": "red",
        "no_data": "yellow",
        "fetch_error": "red",
        "empty_queue": "dim",
    }.get(log.status, "white")

    console.print(f" [dim]node[/]   [bold]{log.node_id}[/]")
    if log.tool:
        console.print(f" [dim]fetched[/] [{log.tool}] {log.target}")
    console.print(f" [dim]status[/] [{status_style}]{log.status}[/]")
    for tool, target in log.new_targets:
        console.print(f" [dim]queued[/] [{tool}] {target}")


def run() -> None:
    cli()
