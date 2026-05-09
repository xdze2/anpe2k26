"""review step — interactive terminal review of eval-scored nodes."""

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

_EVAL_STEP = "eval"
_console = Console()


class ReviewStep:
    name = "review"
    version = "v1"
    description = "Interactive terminal review of eval-scored nodes."
    rate_gate = api_throttles.NONE

    def scan(
        self,
        queue: Queue,
        vault: Vault,
        score: str | None = None,
        **_: object,
    ) -> list[Candidate]:
        """Return one Candidate per eval-done node not yet reviewed.

        score: optional filter, e.g. "good" or "maybe".
        """
        candidates: list[Candidate] = []
        for ev in queue.done_events(_EVAL_STEP):
            outputs = json.loads(ev["outputs"]) if isinstance(ev["outputs"], str) else ev["outputs"]
            eval_uri = outputs.get("eval_uri")
            if not eval_uri:
                continue

            node_id = ev["node_id"]
            ev_score = outputs.get("score", "")
            if score is not None and ev_score != score:
                continue

            args = {"node_id": node_id, "eval_uri": eval_uri}
            if queue.is_done(self.name, self.version, args):
                continue

            candidates.append(Candidate(
                step=self.name,
                node_id=node_id,
                args=args,
                context={"score": ev_score},
            ))

        return candidates

    async def work(self, args: dict, vault: Vault, log: Log) -> dict:  # type: ignore[type-arg]
        node_id = args["node_id"]
        eval_uri = args["eval_uri"]

        eval_data = json.loads(vault.load(eval_uri).decode())
        score = eval_data.get("score", "?")
        fit = eval_data.get("fit", "")
        summary_uri = eval_data.get("summary_uri", "")

        summary = ""
        if summary_uri and vault.exists(summary_uri):
            sum_data = json.loads(vault.load(summary_uri).decode())
            summary = sum_data.get("summary", "")

        _console.print(Rule(f"[bold]{node_id}[/]  score=[cyan]{score}[/]"))
        if fit:
            _console.print(f"  [dim]{fit}[/]")
        _console.print()
        if summary:
            _console.print(Padding(Markdown(summary), pad=(0, 4)))
        _console.print()

        try:
            reaction = input(" > ").strip()
        except (EOFError, KeyboardInterrupt):
            _console.print("\n [dim]Interrupted.[/]")
            raise

        log(f"score={score}  reaction={reaction!r}")

        payload = {
            "node_id": node_id,
            "eval_uri": eval_uri,
            "score": score,
            "reaction": reaction,
        }
        review_uri = vault.store(
            node_id, self.name, node_id[:8], "json",
            json.dumps(payload, indent=2, ensure_ascii=False).encode(),
        )
        log(f"saved → {review_uri}")
        return {"review_uri": review_uri, "reaction": reaction}
