"""Textual TUI for the ANPE chat agent."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable

from pydantic_ai import AgentStreamEvent, FunctionToolCallEvent, RunContext
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Input, Label, RichLog

from anpe.agent import agent
from anpe.config import settings


class AnpeApp(App[None]):
    CSS = """
    #log {
        border: none;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    #input-bar {
        dock: bottom;
        height: 3;
        border-top: solid $panel;
        padding: 0 1;
    }
    #status {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quitter", show=True),
    ]

    TITLE = "ANPE — Assistant Numérique Pour l'Emploi"

    def __init__(self) -> None:
        super().__init__()
        self._tokens_in = 0
        self._tokens_out = 0

    def compose(self) -> ComposeResult:
        yield RichLog(id="log", markup=True, wrap=True, highlight=False)
        yield Input(id="input-bar", placeholder="Tapez votre message...")
        yield Label(self._status_text("prêt"), id="status")

    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        log.write("[bold cyan]ANPE[/] Bonjour ! Comment puis-je vous aider ?")
        self.query_one("#input-bar", Input).focus()

    def _status_text(self, state: str) -> str:
        if self._tokens_in or self._tokens_out:
            token_part = f"dernière requête: {self._tokens_in} → {self._tokens_out} tokens   "
        else:
            token_part = ""
        return f"{token_part}modèle: {settings.openrouter_model}   {state}"

    def _set_status(self, state: str) -> None:
        self.query_one("#status", Label).update(self._status_text(state))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        input_widget = self.query_one("#input-bar", Input)
        input_widget.clear()
        input_widget.disabled = True

        log = self.query_one("#log", RichLog)
        log.write(f"\n[bold green]Vous[/] {text}")

        self._set_status("⟳ en attente...")
        asyncio.create_task(self._run_agent(text))

    async def _run_agent(self, text: str) -> None:
        log = self.query_one("#log", RichLog)

        async def _handle_events(
            ctx: RunContext[None], events: AsyncIterable[AgentStreamEvent]
        ) -> None:
            async for event in events:
                if isinstance(event, FunctionToolCallEvent):
                    log.write(
                        f"[yellow]  ⟳ outil: {event.part.tool_name}[/yellow]"
                    )

        try:
            result = await agent.run(text, event_stream_handler=_handle_events)
            usage = result.usage()
            self._tokens_in = usage.input_tokens or 0
            self._tokens_out = usage.output_tokens or 0
            log.write(f"[bold cyan]ANPE[/] {result.output}")
            self._set_status("prêt")
        except Exception as e:
            log.write(f"[bold red]Erreur[/] {e}")
            self._set_status("erreur")
        finally:
            input_widget = self.query_one("#input-bar", Input)
            input_widget.disabled = False
            input_widget.focus()


def run() -> None:
    AnpeApp().run()
