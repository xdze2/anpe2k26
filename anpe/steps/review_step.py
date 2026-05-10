"""review step — interactive terminal review of summarize_ddg nodes."""

from __future__ import annotations

import json

from rich.console import Console
from rich.markdown import Markdown
from rich.padding import Padding
from rich.rule import Rule

from anpe.engine.queue import Queue
from anpe.steps import api_throttles
from anpe.engine.base import Candidate, Log
from anpe.engine.vault import Vault

_SUMMARIZE_STEP = "summarize_ddg"
_console = Console()


class ReviewStep:
    name = "review"
    version = "v1"
    description = "Interactive terminal review of summarize_ddg nodes."
    rate_gate = api_throttles.NONE

    def scan(
        self,
        queue: Queue,
        vault: Vault,
        **_: object,
    ) -> list[Candidate]:
        """Return one Candidate per summarize_ddg-done node not yet reviewed."""
        candidates: list[Candidate] = []
        for ev in queue.done_events(_SUMMARIZE_STEP):
            outputs = json.loads(ev["outputs"]) if isinstance(ev["outputs"], str) else ev["outputs"]
            summary_uri = outputs.get("summary_uri")
            if not summary_uri:
                continue

            node_id = ev["node_id"]
            args = {"node_id": node_id, "summary_uri": summary_uri}
            if queue.is_done(self.name, self.version, args):
                continue

            candidates.append(Candidate(
                step=self.name,
                node_id=node_id,
                args=args,
            ))

        return candidates

    async def work(self, args: dict, vault: Vault, log: Log) -> dict:  # type: ignore[type-arg]
        node_id = args["node_id"]
        summary_uri = args["summary_uri"]

        sum_data = json.loads(vault.load(summary_uri).decode())
        summary = sum_data.get("summary", "")

        _console.print(Rule(f"[bold]{node_id}[/]"))
        _console.print()
        if summary:
            _console.print(Padding(Markdown(summary), pad=(0, 4)))
        _console.print()

        try:
            reaction = input(" > ").strip()
        except (EOFError, KeyboardInterrupt):
            _console.print("\n [dim]Interrupted.[/]")
            raise

        log(f"reaction={reaction!r}")

        payload = {
            "node_id": node_id,
            "summary_uri": summary_uri,
            "reaction": reaction,
        }
        review_uri = vault.store(
            node_id, self.name, node_id[:8], "json",
            json.dumps(payload, indent=2, ensure_ascii=False).encode(),
        )
        log(f"saved → {review_uri}")
        return {"review_uri": review_uri, "reaction": reaction}
