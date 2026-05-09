"""summarize_ddg step — scan DDG raw artifacts lacking a summary, work calls the LLM."""

from __future__ import annotations

import json

from anpe.engine.queue import Queue
from anpe.steps import api_throttles
from anpe.engine.base import Candidate, Log
from anpe.engine.vault import Vault
from anpe.steps.summarize_fn import SUMMARIZE_VERSION, ddg_summarize
from anpe.tools.naf import _load_csv_index

_TOOL = "ddg"
_DDG_STEP = "fetch_ddg"


class SummarizeDdgStep:
    name = "summarize_ddg"
    version = SUMMARIZE_VERSION + ".2"
    description = "Summarize raw DDG fetch results with an LLM and extract follow-up targets."
    rate_gate = api_throttles.MISTRAL

    def scan(self, queue: Queue, _vault: Vault, **_: object) -> list[Candidate]:
        """Return one Candidate per completed fetch_ddg run not yet summarized."""
        candidates: list[Candidate] = []
        for ev in queue.done_events(_DDG_STEP):
            outputs = json.loads(ev["outputs"]) if isinstance(ev["outputs"], str) else ev["outputs"]
            raw_ddg_uri = outputs.get("raw_uri")
            siren_uri = outputs.get("siren_uri")
            node_id = ev["node_id"]

            if not raw_ddg_uri or not siren_uri:
                continue

            args = {
                "node_id": node_id,
                "raw_ddg_uri": raw_ddg_uri,
                "siren_uri": siren_uri,
            }
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
        raw_ddg_uri = args["raw_ddg_uri"]
        siren_uri = args["siren_uri"]

        log(f"node={node_id}  raw_ddg_uri={raw_ddg_uri}")
        raw_data = vault.load(raw_ddg_uri).decode()
        log(f"loaded {len(raw_data)} chars of DDG data")

        siren_raw = json.loads(vault.load(siren_uri).decode())
        company_profile = _fmt_company_profile(siren_raw)

        result = await ddg_summarize(raw_data, "", company_profile)
        log(f"summarize done  status={result.status}  model={result.model}")

        payload = {
            "status": result.status,
            "summary": result.summary,
            "model": result.model,
            "version": result.version,
            "prompt": result.prompt,
        }
        summary_uri = vault.store(
            node_id, self.name, node_id[:8], "json", json.dumps(payload, indent=2, ensure_ascii=False).encode()
        )
        log(f"saved → {summary_uri}")
        return {"summary_uri": summary_uri, **payload}


def _fmt_company_profile(siren_raw: dict) -> str:  # type: ignore[type-arg]
    naf_index = _load_csv_index()
    naf_code = siren_raw.get("activite_principale", "")
    naf_label = naf_index.get(naf_code, "")

    siege = siren_raw.get("siege", {})
    lines = []
    if name := (siege.get("nom_commercial") or siren_raw.get("nom_complet", "")):
        lines.append(f"Name: {name}")
    if siren := siren_raw.get("siren", ""):
        lines.append(f"Siren: {siren}")
    if naf_code:
        lines.append(f"NAF: {naf_code}" + (f" — {naf_label}" if naf_label else ""))
    if city := siege.get("libelle_commune", ""):
        lines.append(f"City: {city}")
    if headcount := siren_raw.get("tranche_effectif_salarie", ""):
        lines.append(f"Headcount band: {headcount}")
    return "\n".join(lines)
