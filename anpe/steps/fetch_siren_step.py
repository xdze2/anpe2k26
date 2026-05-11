"""fetch_siren step — fetch company registry data from the Recherche Entreprises API."""

from __future__ import annotations

import json

from anpe.engine.queue import Queue
from anpe.steps import api_throttles
from anpe.engine.base import Candidate, FatalError, Log, RetryableError
from collections.abc import Iterator
from anpe.engine.vault import Vault
from anpe.clients.errors import FetchNotFoundError, FetchRetryableError
from anpe.steps.seed_fn import node_id_for

_TOOL = "siren"


class FetchSirenStep:
    name = "fetch_siren"
    version = "v1"
    description = "Fetch company registry data from the Recherche Entreprises API for each company in the bootstrap listing."
    rate_gate = api_throttles.SIREN

    def scan(self, queue: Queue, vault: Vault, **_: object) -> Iterator[Candidate]:
        """Return one Candidate per company in the latest bootstrap listing not yet fetched."""
        events = queue.done_events("bootstrap", newest_first=True)
        if not events:
            return
        outputs = json.loads(events[0]["outputs"]) if isinstance(events[0]["outputs"], str) else events[0]["outputs"]
        listing_uri = outputs.get("listing_uri")
        if not listing_uri:
            return

        listing_text = vault.load(listing_uri).decode()
        for line in listing_text.splitlines():
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
            yield Candidate(
                step=self.name,
                node_id=node_id,
                args=args,
                context={"nom_complet": row["nom_complet"], "siren": row["siren"]},
            )

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
        uri = vault.output_uri(node_id, self.name)
        vault.write(uri, raw_data.encode(), log)
        return {"raw_uri": uri, "siren": siren}

