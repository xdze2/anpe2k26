"""Eval step — scan (node, summary, profile) triples lacking a scored eval."""

from __future__ import annotations

import json
from pathlib import Path

from anpe.engine.queue import Queue
from anpe.engine.steps import api_throttles
from anpe.engine.steps.base import Candidate, Log
from anpe.engine.vault import Vault
from anpe.node_dir import NODES_DIR, NodeDir
from anpe.profile import active_profile_file
from anpe.prospect.eval import EVAL_VERSION, llm_eval


class EvalStep:
    name = "eval"
    version = EVAL_VERSION
    description = "Score each summarized company against the user profile and assign a fit level."
    rate_gate = api_throttles.MISTRAL

    def scan(
        self,
        queue: Queue,
        _vault: Vault,
        *,
        min_score: str | None = None,
        exclude_reaction: str | None = None,
        **_: object,
    ) -> list[Candidate]:
        """Return one Candidate per (node, sum_uri, profile_uri) with no matching eval.

        filter_flags:
          min_score        — only emit if latest eval score is >= this value
                             (order: discard < enrich < maybe < good).
                             Nodes with no prior eval are always included.
          exclude_reaction — skip nodes whose latest reaction matches this string
                             (e.g. "discard").
        """
        profile_path = active_profile_file()
        if profile_path is None:
            return []
        profile_uri = str(profile_path)

        if not NODES_DIR.exists():
            return []

        candidates: list[Candidate] = []
        for node_path in sorted(NODES_DIR.iterdir()):
            if not node_path.is_dir():
                continue
            node_id = node_path.name
            node = NodeDir(node_id)

            # Filter by reaction
            if exclude_reaction is not None:
                review = node.get_latest_review()
                if review and review.get("reaction") == exclude_reaction:
                    continue

            sum_file = node.get_latest_sum_file()
            if sum_file is None:
                continue

            sum_uri = f"{node_id}/summarize/{sum_file}"

            # Check whether an eval for this (sum_uri, profile_uri, version) already exists.
            if _has_eval_for(node, sum_uri, profile_uri, EVAL_VERSION):
                continue

            # Filter by min_score — only applies when a prior eval exists.
            if min_score is not None:
                latest = node.get_latest_eval_result()
                if latest is not None:
                    if not _score_gte(latest.get("score", ""), min_score):
                        continue

            # Surface context signals for downstream filtering.
            latest_eval = node.get_latest_eval_result()
            candidates.append(Candidate(
                step=self.name,
                node_id=node_id,
                args={"sum_uri": sum_uri, "profile_uri": profile_uri},
                context={
                    "score": latest_eval.get("score", "") if latest_eval else "",
                    "reaction": (node.get_latest_review() or {}).get("reaction", ""),
                    "naf": node.get_siren_meta().get("naf", ""),
                },
            ))

        return candidates

    async def work(self, args: dict, vault: Vault, log: Log) -> dict:  # type: ignore[type-arg]
        sum_uri = args["sum_uri"]
        profile_uri = args["profile_uri"]

        log(f"sum_uri={sum_uri}  profile_uri={profile_uri}")

        # sum_uri is a relative path like "{node_id}/summarize/{file}"
        # The file lives in user_data/nodes/ (existing system), not the vault.
        node_id, _, sum_file = sum_uri.partition("/summarize/")
        sum_path = NODES_DIR / node_id / "summarize" / sum_file
        sum_data = json.loads(sum_path.read_text(encoding="utf-8"))
        summary = sum_data.get("summary", "")

        profile_text = Path(profile_uri).read_text(encoding="utf-8")
        log(f"calling llm_eval  summary_len={len(summary)}  profile_len={len(profile_text)}")

        result = await llm_eval(summary, profile_text)
        log(f"eval done  score={result.score}  uncertainty={result.uncertainty}")
        return {
            "score": result.score,
            "fit": result.fit,
            "dealbreakers": result.dealbreakers,
            "uncertainty": result.uncertainty,
        }


_SCORE_ORDER = {"discard": 0, "enrich": 1, "maybe": 2, "good": 3}


def _score_gte(score: str, minimum: str) -> bool:
    return _SCORE_ORDER.get(score, -1) >= _SCORE_ORDER.get(minimum, 0)


def _has_eval_for(node: NodeDir, sum_uri: str, profile_uri: str, version: str) -> bool:
    """True if an eval result for this (sum_uri, profile_uri, version) already exists."""
    eval_dir = node.path / "eval_results"
    if not eval_dir.exists():
        return False
    for f in eval_dir.glob("eval_*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if (
                data.get("sum_file", "").endswith(sum_uri.split("/summarize/")[-1])
                and data.get("profile_file") == profile_uri
                and data.get("eval_version") == version
            ):
                return True
        except Exception:
            continue
    return False
