"""review step — interactive terminal review of summarize_ddg nodes."""

from __future__ import annotations

import json

import questionary
from rich.console import Console
from rich.markdown import Markdown
from rich.padding import Padding
from rich.rule import Rule

from anpe.engine.base import Candidate, Log, RetryableError
from anpe.engine.queue import Queue
from anpe.engine.vault import Vault
from anpe.steps import api_throttles
from anpe.steps.view import node_view

_CHOICES = [
    questionary.Choice("interested", value="interested"),
    questionary.Choice("not interested", value="not_interested"),
    questionary.Choice("more data", value="more_data"),
    questionary.Choice("skip", value="skip"),
]

_SUMMARIZE_STEP = "summarize_ddg"
_SIREN_STEP = "fetch_siren"
_EVAL_STEP = "eval"
_console = Console()


def _latest_outputs(queue: Queue, node_id: str, step: str) -> dict | None:  # type: ignore[type-arg]
    for row in reversed(queue.node_history(node_id, step=step)):
        if row["event"] == "done":
            raw = row["outputs"]
            result: dict = json.loads(raw) if isinstance(raw, str) else raw  # type: ignore[type-arg]
            return result
    return None


class ReviewStep:
    name = "review"
    version = "v1.1"
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
            outputs = (
                json.loads(ev["outputs"])
                if isinstance(ev["outputs"], str)
                else ev["outputs"]
            )
            summary_uri = outputs.get("summary_uri")
            if not summary_uri:
                continue

            node_id = ev["node_id"]

            siren_outputs = _latest_outputs(queue, node_id, _SIREN_STEP)
            siren_uri = siren_outputs.get("raw_uri") if siren_outputs else None

            eval_outputs = _latest_outputs(queue, node_id, _EVAL_STEP)
            eval_uri = eval_outputs.get("eval_uri") if eval_outputs else None

            args = {
                "node_id": node_id,
                "summary_uri": summary_uri,
                "siren_uri": siren_uri,
                "eval_uri": eval_uri,
            }
            if queue.is_done(self.name, self.version, args):
                continue

            candidates.append(
                Candidate(
                    step=self.name,
                    node_id=node_id,
                    args=args,
                )
            )

        return candidates

    def work(self, args: dict, vault: Vault, log: Log) -> dict:  # type: ignore[type-arg]
        node_id = args["node_id"]
        summary_uri = args["summary_uri"]
        siren_uri = args.get("siren_uri")
        eval_uri = args.get("eval_uri")

        md = node_view(vault, summary_uri, siren_uri=siren_uri, eval_uri=eval_uri)
        _console.print(Rule(f"[bold]{node_id}[/]"))
        _console.print()
        _console.print(Padding(Markdown(md), pad=(0, 4)))
        _console.print()

        reaction = questionary.select("Reaction?", choices=_CHOICES).ask()
        if reaction is None or reaction == "skip":
            _console.print("[dim]skipped.[/]")
            raise RetryableError("skipped")

        log(f"reaction={reaction!r}")

        payload = {
            "node_id": node_id,
            "summary_uri": summary_uri,
            "siren_uri": siren_uri,
            "eval_uri": eval_uri,
            "reaction": reaction,
        }
        review_uri = vault.store(
            node_id,
            self.name,
            node_id[:8],
            "json",
            json.dumps(payload, indent=2, ensure_ascii=False).encode(),
        )
        log(f"saved → {review_uri}")
        return {"review_uri": review_uri, "reaction": reaction}
