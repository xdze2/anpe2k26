"""fetch_ddg step — fetch DuckDuckGo search results for each company with siren data."""

from __future__ import annotations

import json
from collections.abc import Iterator

from anpe.clients.errors import FetchBlockedError, FetchNotFoundError, FetchRetryableError
from anpe.engine.types import Candidate, FatalError, Log, RetryableError
from anpe.engine.vault import Vault

_SIREN_STEP = "fetch_siren"


def _ddg_target(siren_raw: dict) -> str:  # type: ignore[type-arg]
    """Derive the DDG search query from siren registry data."""
    siege = siren_raw.get("siege", {})
    nom_legal = siren_raw.get("nom_complet", "")
    nom_commercial = str(siege.get("nom_commercial") or nom_legal)
    naf_section = str(siren_raw.get("section_activite_principale", ""))
    suffix = " entreprise informatique" if naf_section == "J" else " entreprise"
    return nom_commercial + suffix


class FetchDdgStep:
    name = "fetch_ddg"

    def __init__(self) -> None:
        from anpe.clients.ddg import DdgClient

        self._fetch = DdgClient(min_interval_s=2.0)

    def scan(
        self, vault: Vault, overwrite: bool = False, **_: object
    ) -> Iterator[Candidate]:
        """Yield one Candidate per node that has fetch_siren output."""
        nodes_dir = vault.root / "nodes"
        if not nodes_dir.exists():
            return

        for siren_path in sorted(nodes_dir.glob(f"*/{_SIREN_STEP}_*.json")):
            node_id = siren_path.parent.name
            siren_uri = str(siren_path.relative_to(vault.root))

            siren_raw = json.loads(siren_path.read_text())
            target = _ddg_target(siren_raw)

            ddg_uri = vault.output_uri(node_id, self.name)
            yield Candidate(
                node_id=node_id,
                args={"node_id": node_id, "siren_uri": siren_uri, "target": target},
                skip=vault.exists(ddg_uri) and not overwrite,
            )

    def work(self, args: dict, vault: Vault, log: Log) -> None:  # type: ignore[type-arg]
        node_id = args["node_id"]
        target = args["target"]

        log(f"fetching DDG target={target!r}  node={node_id}")
        try:
            raw_data = self._fetch(target)
        except FetchNotFoundError as e:
            log(f"not_found: {e}")
            raise FatalError(f"not_found: {e}") from e
        except FetchBlockedError as e:
            log(f"blocked: {e}")
            raise RetryableError(f"blocked: {e}") from e
        except FetchRetryableError as e:
            log(f"retryable error: {e}")
            raise RetryableError(f"retryable: {e}") from e

        log(f"fetched {len(raw_data)} chars")
        uri = vault.output_uri(node_id, self.name)
        vault.write(uri, raw_data.encode(), log)
