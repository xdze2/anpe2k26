"""fetch_siren step — fetch company registry data from the Recherche Entreprises API."""

from __future__ import annotations

import json
from collections.abc import Iterator

from anpe.engine.types import Candidate, FatalError, Log, RetryableError
from anpe.engine.vault import Vault
from anpe.clients.errors import FetchNotFoundError, FetchRetryableError
from anpe.steps.seed_fn import node_id_for

_LISTING_URI = "listing.jsonl"


class FetchSirenStep:
    name = "fetch_siren"

    def __init__(self) -> None:
        from anpe.clients.siren import SirenClient

        self._fetch = SirenClient(min_interval_s=1.0)

    def scan(
        self, vault: Vault, overwrite: bool = False, **_: object
    ) -> Iterator[Candidate]:
        """Yield one Candidate per company in listing.jsonl not yet fetched."""
        if not vault.exists(_LISTING_URI):
            return

        listing_text = vault.load(_LISTING_URI).decode()
        for line in listing_text.splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            node_id = node_id_for(row["nom_complet"], row["siren"])
            uri = vault.output_uri(node_id, self.name)
            yield Candidate(
                node_id=node_id,
                args={"node_id": node_id, "siren": row["siren"]},
                skip=vault.exists(uri) and not overwrite,
            )

    def work(self, args: dict, vault: Vault, log: Log) -> None:  # type: ignore[type-arg]
        node_id = args["node_id"]
        siren = args["siren"]

        log(f"fetching siren={siren!r}  node={node_id}")
        try:
            raw_data = self._fetch(siren)
        except FetchNotFoundError as e:
            log(f"not_found: {e}")
            raise FatalError(f"not_found: {e}") from e
        except FetchRetryableError as e:
            log(f"retryable error: {e}")
            raise RetryableError(f"retryable: {e}") from e

        log(f"fetched {len(raw_data)} chars")
        uri = vault.output_uri(node_id, self.name)
        vault.write(uri, raw_data.encode(), log)
