import asyncio

import click

from anpe.agent import agent


@click.command()
def chat() -> None:
    """Start an interactive chat session with ANPE."""
    asyncio.run(_chat_loop())


async def _chat_loop() -> None:
    click.echo("ANPE — Assistant Numérique Pour l'Emploi")
    click.echo("Tapez 'quit' pour quitter.\n")

    while True:
        user_input = click.prompt("Vous", prompt_suffix=": ").strip()
        if user_input.lower() in {"quit", "exit", "q"}:
            break
        if not user_input:
            continue

        result = await agent.run(user_input)
        click.echo(f"ANPE: {result.output}\n")
