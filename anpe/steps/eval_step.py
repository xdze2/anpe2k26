"""Eval step — scan (node, summary, profile) triples lacking a scored eval."""

from __future__ import annotations

import json

from anpe.engine.queue import Queue
from anpe.steps import api_throttles
from pydantic import ValidationError

from anpe.engine.base import Candidate, Log, RetryableError
from collections.abc import Iterator
from anpe.engine.vault import Vault
from anpe.steps.eval_fn import EVAL_VERSION, llm_eval

_PROFILE_URI = "user_preference.md"
_SUMMARIZE_STEP = "summarize_ddg"


class EvalStep:
    name = "eval"
    version = EVAL_VERSION + ".3"
    description = (
        "Score each summarized company against the user profile and assign a fit level."
    )
    rate_gate = api_throttles.MISTRAL

    def scan(
        self,
        queue: Queue,
        vault: Vault,
        **_: object,
    ) -> Iterator[Candidate]:
        """Return one Candidate per completed summarize_ddg run not yet evaluated.

        # TODO: add min_score filter (requires reading prior eval done events)
        # TODO: add exclude_reaction filter (requires reactions stored in queue)
        """
        if not vault.exists(_PROFILE_URI):
            return

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
            args = {
                "node_id": node_id,
                "summary_uri": summary_uri,
                "profile_uri": _PROFILE_URI,
            }
            if queue.is_done(self.name, self.version, args):
                continue

            # TODO: surface score, reaction, naf in context for future filter flags
            yield Candidate(
                step=self.name,
                node_id=node_id,
                args=args,
                context={},
            )

    async def work(self, args: dict, vault: Vault, log: Log) -> dict:  # type: ignore[type-arg]
        node_id = args["node_id"]
        summary_uri = args["summary_uri"]
        profile_uri = args["profile_uri"]

        log(f"summary_uri={summary_uri}  profile_uri={profile_uri}")

        sum_data = json.loads(vault.load(summary_uri).decode())
        summary = sum_data.get("summary", "")

        profile_text = vault.load(profile_uri).decode()
        log(
            f"calling llm_eval  summary_len={len(summary)}  profile_len={len(profile_text)}"
        )

        try:
            result = await llm_eval(summary, profile_text)
        except ValidationError as e:
            raise RetryableError(f"LLM returned invalid JSON structure: {e}") from e
        log(f"eval done  score={result.score}  uncertainty={result.uncertainty}")

        payload = {
            "score": result.score,
            "fit": result.fit,
            "dealbreakers": result.dealbreakers,
            "uncertainty": result.uncertainty,
            "summary_uri": summary_uri,
            "profile_uri": profile_uri,
            "prompt": result.prompt,
        }
        eval_uri = vault.store(
            node_id,
            self.name,
            node_id[:8],
            "json",
            json.dumps(payload, indent=2, ensure_ascii=False).encode(),
        )
        log(f"saved → {eval_uri}")
        return {"eval_uri": eval_uri, **payload}
