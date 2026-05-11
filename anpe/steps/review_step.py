"""review step — interactive terminal review of summarize_ddg nodes."""

from __future__ import annotations

import json
import random
from collections.abc import Iterator

import questionary
from rich.console import Console
from rich.markdown import Markdown
from rich.padding import Padding
from rich.rule import Rule

from anpe.engine.types import Candidate, FatalError, Log, RetryableError
from anpe.engine.vault import Vault
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


class ReviewStep:
    name = "review"

    def scan(
        self,
        vault: Vault,
        overwrite: bool = False,
        keep_non_relevant: bool = False,
        random_order: bool = False,
        **_: object,
    ) -> Iterator[Candidate]:
        nodes_dir = vault.root / "nodes"
        if not nodes_dir.exists():
            return

        candidates: list[Candidate] = []
        for summary_path in sorted(nodes_dir.glob(f"*/{_SUMMARIZE_STEP}_*.json")):
            node_id = summary_path.parent.name
            summary_uri = str(summary_path.relative_to(vault.root))

            if not keep_non_relevant:
                try:
                    data = json.loads(summary_path.read_bytes())
                    if data.get("status") == "not_relevant":
                        continue
                except Exception:
                    pass

            siren_uri: str | None = None
            siren_paths = list(summary_path.parent.glob(f"{_SIREN_STEP}_*.json"))
            if siren_paths:
                siren_uri = str(siren_paths[0].relative_to(vault.root))

            eval_uri: str | None = None
            eval_paths = list(summary_path.parent.glob(f"{_EVAL_STEP}_*.json"))
            if eval_paths:
                eval_uri = str(eval_paths[0].relative_to(vault.root))

            review_uri = vault.output_uri(node_id, self.name)
            candidates.append(
                Candidate(
                    node_id=node_id,
                    args={
                        "node_id": node_id,
                        "summary_uri": summary_uri,
                        "siren_uri": siren_uri,
                        "eval_uri": eval_uri,
                    },
                    skip=vault.exists(review_uri) and not overwrite,
                )
            )

        if random_order:
            pending = [c for c in candidates if not c.skip]
            done = [c for c in candidates if c.skip]
            random.shuffle(pending)
            yield from done
            yield from pending
        else:
            yield from candidates

    def work(self, args: dict, vault: Vault, log: Log) -> None:  # type: ignore[type-arg]
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
        if reaction is None:
            _console.print("[dim]aborted.[/]")
            raise FatalError("user quit")
        if reaction == "skip":
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
        review_uri = vault.output_uri(node_id, self.name)
        vault.write(
            review_uri,
            json.dumps(payload, indent=2, ensure_ascii=False).encode(),
            log,
        )
