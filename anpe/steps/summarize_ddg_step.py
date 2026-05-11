"""summarize_ddg step — call the LLM to summarize DDG results for each company."""

from __future__ import annotations

import json
from collections.abc import Iterator

from anpe.engine.types import Candidate, FatalError, Log
from anpe.engine.vault import Vault
from anpe.steps.summarize_fn import SUMMARIZE_VERSION, ddg_summarize
from anpe.tools.naf import _load_csv_index

_DDG_STEP = "fetch_ddg"
_SIREN_STEP = "fetch_siren"


class SummarizeDdgStep:
    name = "summarize_ddg"

    def scan(
        self, vault: Vault, overwrite: bool = False, **_: object
    ) -> Iterator[Candidate]:
        """Yield one Candidate per node that has fetch_ddg output."""
        nodes_dir = vault.root / "nodes"
        if not nodes_dir.exists():
            return

        for ddg_path in sorted(nodes_dir.glob(f"*/{_DDG_STEP}_*.json")):
            node_id = ddg_path.parent.name
            ddg_uri = str(ddg_path.relative_to(vault.root))

            siren_uri = vault.output_uri(node_id, _SIREN_STEP)

            summary_uri = vault.output_uri(node_id, self.name)
            yield Candidate(
                node_id=node_id,
                args={
                    "node_id": node_id,
                    "ddg_uri": ddg_uri,
                    "siren_uri": siren_uri,
                },
                skip=vault.exists(summary_uri) and not overwrite,
            )

    def work(self, args: dict, vault: Vault, log: Log) -> None:  # type: ignore[type-arg]
        node_id = args["node_id"]
        ddg_uri = args["ddg_uri"]
        siren_uri = args["siren_uri"]

        log(f"node={node_id}  ddg_uri={ddg_uri}")

        if not vault.exists(siren_uri):
            log(f"missing siren data: {siren_uri}")
            raise FatalError(f"missing siren data: {siren_uri}")

        raw_data = vault.load(ddg_uri).decode()
        log(f"loaded {len(raw_data)} chars of DDG data")

        siren_raw = json.loads(vault.load(siren_uri).decode())
        company_profile = _fmt_company_profile(siren_raw)

        try:
            result = ddg_summarize(raw_data, "", company_profile)
        except ValueError as e:
            log(f"summarize error: {e}")
            payload = {"status": "error", "error": str(e)}
            uri = vault.output_uri(node_id, self.name)
            vault.write(uri, json.dumps(payload, indent=2, ensure_ascii=False).encode(), log)
            return

        log(f"summarize done  status={result.status}  model={result.model}")

        payload = {
            "status": result.status,
            "summary": result.summary,
            "model": result.model,
            "version": result.version,
            "prompt": result.prompt,
        }
        uri = vault.output_uri(node_id, self.name)
        vault.write(uri, json.dumps(payload, indent=2, ensure_ascii=False).encode(), log)


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


SUMMARIZE_VERSION = SUMMARIZE_VERSION  # re-export for tests
