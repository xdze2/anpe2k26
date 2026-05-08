"""fetch_ddg step — scan bootstrap listing, run DDG search."""

from __future__ import annotations

import json

from anpe.engine.queue import Queue
from anpe.engine.steps.base import Candidate, Log
from anpe.engine.vault import Vault
from anpe.prospect.errors import FetchBlockedError, FetchNotFoundError, FetchRetryableError
from anpe.prospect.registry import FETCH_TOOLS
from anpe.prospect.seed import node_id_for

_TOOL = "ddg"
_BOOTSTRAP_NODE = "_bootstrap"
_BOOTSTRAP_STEP = "bootstrap"


class FetchDdgStep:
    name = "fetch_ddg"
    version = "v1"
    description = "Fetch raw DDG search results for companies from the bootstrap listing or follow-up targets."

    def scan(self, queue: Queue, vault: Vault, count: int = 10, **_: object) -> list[Candidate]:
        """Return one Candidate per company in the latest bootstrap listing not yet fetched."""
        listing_uri = _latest_bootstrap_listing_uri(queue)
        if listing_uri is None:
            return []

        listing_text = vault.load(listing_uri).decode()
        candidates: list[Candidate] = []
        for line in listing_text.splitlines():
            if len(candidates) >= count:
                break
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            node_id = node_id_for(row["nom_complet"], row["siren"])
            args = {
                "node_id": node_id,
                "tool": _TOOL,
                "target": row["nom_complet"],
                "listing_uri": listing_uri,
            }
            if queue.is_done(self.name, self.version, args):
                continue
            candidates.append(Candidate(
                step=self.name,
                node_id=node_id,
                args=args,
                context={"nom_complet": row["nom_complet"], "siren": row["siren"]},
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


def _latest_bootstrap_listing_uri(queue: Queue) -> str | None:
    """Return the listing_uri from the most recent successfully completed bootstrap run, or None."""
    events = queue.node_history(_BOOTSTRAP_NODE, step=_BOOTSTRAP_STEP)
    for ev in reversed(events):
        if ev["event"] == "done" and ev.get("outputs"):
            outputs = json.loads(ev["outputs"]) if isinstance(ev["outputs"], str) else ev["outputs"]
            uri = outputs.get("listing_uri")
            if uri:
                return str(uri)
    return None
