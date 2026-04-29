import asyncio
from collections.abc import AsyncIterable

import click
from pydantic_ai import AgentStreamEvent, FunctionToolCallEvent, RunContext
from pydantic_ai.exceptions import ModelHTTPError

from anpe.agent import agent


@click.command()
def chat() -> None:
    """Start an interactive chat session with ANPE."""
    asyncio.run(_chat_loop())


async def _log_tool_calls(ctx: RunContext[None], events: AsyncIterable[AgentStreamEvent]) -> None:
    async for event in events:
        if isinstance(event, FunctionToolCallEvent):
            click.echo(click.style(f"  [outil] {event.part.tool_name}", fg="yellow"))


async def _chat_loop() -> None:
    click.echo("ANPE — Assistant Numérique Pour l'Emploi")
    click.echo("Tapez 'quit' pour quitter.\n")

    while True:
        user_input = click.prompt("Vous", prompt_suffix=": ").strip()
        if user_input.lower() in {"quit", "exit", "q"}:
            break
        if not user_input:
            continue

        try:
            result = await agent.run(user_input, event_stream_handler=_log_tool_calls)
            click.echo(f"ANPE: {result.output}\n")
        except ModelHTTPError as e:
            if e.status_code == 429:
                raw = (e.body or {}).get("metadata", {}).get("raw", "")
                msg = raw or "Trop de requêtes, réessayez dans quelques instants."
                raise click.ClickException(f"Erreur 429: {msg}") from e
            raise click.ClickException(f"Erreur API {e.status_code}: {e}") from e
