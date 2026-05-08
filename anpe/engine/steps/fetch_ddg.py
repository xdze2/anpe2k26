"""fetch_ddg step — scan fetch_siren done events, run DDG search."""

from __future__ import annotations

import json

from anpe.engine.queue import Queue
from anpe.engine.steps.base import Candidate, Log
from anpe.engine.vault import Vault
from anpe.prospect.errors import FetchBlockedError, FetchNotFoundError, FetchRetryableError
from anpe.prospect.registry import FETCH_TOOLS

_TOOL = "ddg"
_SIREN_STEP = "fetch_siren"
_SIREN_VERSION = "v1"


class FetchDdgStep:
    name = "fetch_ddg"
    version = "v1"
    description = "Fetch raw DDG search results for companies sourced from completed fetch_siren runs."

    def scan(self, queue: Queue, vault: Vault, count: int = 10, **_: object) -> list[Candidate]:
        """Return one Candidate per completed fetch_siren run not yet fetched via DDG."""
        candidates: list[Candidate] = []
        for ev in _siren_done_events(queue):
            if len(candidates) >= count:
                break
            outputs = json.loads(ev["outputs"]) if isinstance(ev["outputs"], str) else ev["outputs"]
            siren_uri = outputs.get("raw_uri")
            if not siren_uri:
                continue
            node_id = ev["node_id"]

            siren_raw = json.loads(vault.load(siren_uri).decode())
            target = _ddg_target(siren_raw)

            args = {
                "node_id": node_id,
                "tool": _TOOL,
                "target": target,
                "siren_uri": siren_uri,
            }
            if queue.is_done(self.name, self.version, args):
                continue
            candidates.append(Candidate(
                step=self.name,
                node_id=node_id,
                args=args,
                context={"nom_complet": siren_raw.get("nom_complet", "")},
            ))
        return candidates

    async def work(self, args: dict, vault: Vault, log: Log) -> dict:  # type: ignore[type-arg]
        node_id = args["node_id"]
        target = args["target"]
        fetch_tool = FETCH_TOOLS[_TOOL]

        log(f"fetching [{_TOOL}] {target!r}  node={node_id}")
        try:
            raw_data = fetch_tool.fetch(target)
        except FetchNotFoundError as e:
            log(f"not_found: {e}")
            raise ValueError(f"not_found: {e}") from e
        except FetchRetryableError as e:
            log(f"retryable error: {e}")
            raise RuntimeError(f"retryable: {e}") from e
        except FetchBlockedError as e:
            log(f"blocked: {e}")
            raise RuntimeError(f"blocked: {e}") from e

        log(f"fetched {len(raw_data)} chars")
        uri = vault.store(node_id, self.name, node_id[:8], fetch_tool.raw_ext, raw_data.encode())
        log(f"saved → {uri}")
        return {"raw_uri": uri, "tool": _TOOL, "target": target}


def _siren_done_events(queue: Queue) -> list[dict]:  # type: ignore[type-arg]
    """Return all fetch_siren done events, ordered by id."""
    rows = queue._conn.execute(
        "SELECT node_id, outputs FROM events WHERE step = ? AND event = 'done' ORDER BY id",
        (_SIREN_STEP,),
    ).fetchall()
    return [{"node_id": r[0], "outputs": r[1]} for r in rows]


def _ddg_target(siren_raw: dict) -> str:  # type: ignore[type-arg]
    """Derive the DDG search query from siren registry data."""
    siege = siren_raw.get("siege", {})
    nom_legal = siren_raw.get("nom_complet", "")
    nom_commercial = str(siege.get("nom_commercial") or nom_legal)
    naf_section = str(siren_raw.get("section_activite_principale", ""))
    suffix = " entreprise informatique" if naf_section == "J" else " entreprise"
    return nom_commercial + suffix
