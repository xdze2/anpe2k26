"""summarize_ddg step — scan DDG raw artifacts lacking a summary, work calls the LLM."""

from __future__ import annotations

import json
import pathlib

from anpe.engine.queue import Queue
from anpe.engine.steps.base import Candidate, Log
from anpe.engine.vault import Vault
from anpe.node_dir import NODES_DIR, NodeDir
from anpe.prospect.registry import FETCH_TOOLS
from anpe.prospect.summarize import SUMMARIZE_VERSION

_TOOL = "ddg"


class SummarizeDdgStep:
    name = "summarize_ddg"
    version = SUMMARIZE_VERSION
    description = "Summarize raw DDG fetch results with an LLM and extract follow-up targets."

    def scan(self, queue: Queue, _vault: Vault, *, naf_prefix: str | None = None, **_: object) -> list[Candidate]:
        """Return one Candidate per (node, raw_uri) DDG pair with no matching summary.

        filter_flags:
          naf_prefix — if set, only emit candidates whose node's NAF code starts
                       with that prefix (e.g. "62" for software/IT).
        """
        if not NODES_DIR.exists():
            return []

        fetch_tool = FETCH_TOOLS[_TOOL]

        candidates: list[Candidate] = []
        for node_path in sorted(NODES_DIR.iterdir()):
            if not node_path.is_dir():
                continue
            node_id = node_path.name
            node = NodeDir(node_id)

            if naf_prefix is not None:
                meta = node.get_siren_meta()
                if not meta.get("naf", "").startswith(naf_prefix):
                    continue

            fetch_file = node_path / "fetch.jsonl"
            if not fetch_file.exists():
                continue

            events = [
                json.loads(line)
                for line in fetch_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            puts: dict[str, dict] = {}  # type: ignore[type-arg]
            latest: dict[str, dict] = {}  # type: ignore[type-arg]
            for ev in events:
                uid = ev.get("uid", "")
                if ev["event"] == "put":
                    puts[uid] = ev
                latest[uid] = ev

            for uid, put_ev in puts.items():
                if put_ev.get("tool") != _TOOL:
                    continue
                last = latest.get(uid, put_ev)
                if last["event"] != "fetch_done":
                    continue

                raw_file = last.get("raw_file", "")
                sum_dir = node_path / "summarize"
                if _has_summary_for(sum_dir, uid, fetch_tool.version):
                    continue

                raw_uri = f"{node_id}/raw_data/{raw_file}"
                candidates.append(Candidate(
                    step=self.name,
                    node_id=node_id,
                    args={
                        "uid": uid,
                        "tool": _TOOL,
                        "target": put_ev.get("target", ""),
                        "raw_uri": raw_uri,
                    },
                    context={"naf": node.get_siren_meta().get("naf", "")},
                ))

        return candidates

    async def work(self, args: dict, vault: Vault, log: Log) -> dict:  # type: ignore[type-arg]
        node_id = args["node_id"]
        raw_uri = args["raw_uri"]

        log(f"node={node_id}  raw_uri={raw_uri}")
        fetch_tool = FETCH_TOOLS[_TOOL]
        raw_data = vault.load(raw_uri).decode()
        log(f"loaded {len(raw_data)} chars from vault")
        node = NodeDir(node_id)
        previous_summary = node.get_latest_summary()
        company_profile = _fmt_company_profile(node.get_siren_meta())

        result = await fetch_tool.summarize(raw_data, previous_summary, company_profile)
        log(f"summarize done  status={result.status}  model={result.model}  new_targets={len(result.new_targets)}")
        return {
            "status": result.status,
            "summary": result.summary,
            "new_targets": [{"tool": t.tool, "target": t.target} for t in result.new_targets],
            "model": result.model,
            "version": result.version,
        }


def _has_summary_for(sum_dir: pathlib.Path, uid: str, version: str) -> bool:
    """True if sum_dir contains a result file for this uid at this version."""
    if not sum_dir.exists():
        return False
    for f in sum_dir.glob("sum_*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("fetch_uid") == uid and data.get("summarize_version") == version:
                return True
        except Exception:
            continue
    return False


def _fmt_company_profile(fm: dict) -> str:  # type: ignore[type-arg]
    keys = ["name", "siren", "naf", "category", "headcount", "city"]
    lines = [f"{k.capitalize()}: {fm[k]}" for k in keys if k in fm]
    return "\n".join(lines)
