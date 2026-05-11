"""Eval step — score each summarized company against the user profile."""

from __future__ import annotations

import json
from collections.abc import Iterator

from pydantic import ValidationError

from anpe.engine.types import Candidate, FatalError, Log, RetryableError
from anpe.engine.vault import Vault
from anpe.steps.eval_fn import llm_eval

_SUMMARIZE_STEP = "summarize_ddg"
_PROFILE_URI = "user_preference.md"


class EvalStep:
    name = "eval"

    def scan(
        self,
        vault: Vault,
        overwrite: bool = False,
        keep_non_relevant: bool = False,
        **_: object,
    ) -> Iterator[Candidate]:
        nodes_dir = vault.root / "nodes"
        if not nodes_dir.exists():
            return

        if not vault.exists(_PROFILE_URI):
            return

        for summary_path in sorted(nodes_dir.glob(f"*/{_SUMMARIZE_STEP}_*.json")):
            node_id = summary_path.parent.name
            summary_uri = str(summary_path.relative_to(vault.root))

            is_not_relevant = False
            if not keep_non_relevant:
                data = json.loads(summary_path.read_bytes())
                is_not_relevant = data.get("status") == "not_relevant"

            eval_uri = vault.output_uri(node_id, self.name)
            yield Candidate(
                node_id=node_id,
                args={
                    "node_id": node_id,
                    "summary_uri": summary_uri,
                    "profile_uri": _PROFILE_URI,
                },
                skip=is_not_relevant or (vault.exists(eval_uri) and not overwrite),
            )

    def work(self, args: dict, vault: Vault, log: Log) -> None:  # type: ignore[type-arg]
        node_id = args["node_id"]
        summary_uri = args["summary_uri"]
        profile_uri = args["profile_uri"]

        log(f"node={node_id}  summary_uri={summary_uri}")

        sum_data = json.loads(vault.load(summary_uri).decode())
        summary = sum_data.get("summary", "")

        if not vault.exists(profile_uri):
            raise FatalError(f"missing profile: {profile_uri}")

        profile_text = vault.load(profile_uri).decode()
        log(
            f"calling llm_eval  summary_len={len(summary)}  profile_len={len(profile_text)}"
        )

        try:
            result = llm_eval(summary, profile_text)
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
        eval_uri = vault.output_uri(node_id, self.name)
        vault.write(
            eval_uri, json.dumps(payload, indent=2, ensure_ascii=False).encode(), log
        )
