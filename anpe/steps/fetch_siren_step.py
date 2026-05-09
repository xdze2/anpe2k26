"""fetch_siren step — fetch company registry data from the Recherche Entreprises API."""

from __future__ import annotations

import json

from anpe.engine.queue import Queue
from anpe.steps import api_throttles
from anpe.engine.base import Candidate, FatalError, Log, RetryableError
from anpe.engine.vault import Vault
from anpe.clients.errors import FetchNotFoundError, FetchRetryableError
from anpe.steps.seed_fn import node_id_for

_TOOL = "siren"
_BOOTSTRAP_NODE = "_bootstrap"
_BOOTSTRAP_STEP = "bootstrap"


class FetchSirenStep:
    name = "fetch_siren"
    version = "v1"
    description = "Fetch company registry data from the Recherche Entreprises API for each company in the bootstrap listing."
    rate_gate = api_throttles.SIREN

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
                "target": row["siren"],
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
        from anpe.clients.siren import siren_fetch

        node_id = args["node_id"]
        siren = args["target"]

        log(f"fetching siren={siren!r}  node={node_id}")
        try:
            raw_data = siren_fetch(siren)
        except FetchNotFoundError as e:
            log(f"not_found: {e}")
            raise FatalError(f"not_found: {e}") from e
        except FetchRetryableError as e:
            log(f"retryable error: {e}")
            raise RetryableError(f"retryable: {e}") from e

        log(f"fetched {len(raw_data)} chars")
        uri = vault.store(node_id, self.name, node_id[:8], "json", raw_data.encode())
        log(f"saved → {uri}")
        return {"raw_uri": uri, "siren": siren}


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
