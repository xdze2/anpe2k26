"""bootstrap step — scan seed_query.yaml, produce company listing JSONL in vault."""

from __future__ import annotations

import hashlib

from anpe.steps.bootstrap.pipeline import rows_to_jsonl_bytes, run as _pipeline_run
from anpe.engine.queue import Queue
from anpe.steps import api_throttles
from anpe.engine.base import Candidate, Log
from anpe.engine.vault import Vault

_SEED_URI = "seed_query.yaml"


class BootstrapStep:
    name = "bootstrap"
    version = "v2"
    description = "From seed_query.yaml produce a company listing JSONL in the vault."
    rate_gate = api_throttles.NONE

    def scan(
        self, queue: Queue, vault: Vault, refresh: bool = False, **_: object
    ) -> list[Candidate]:
        """Emit one candidate keyed on the profile's content hash.

        Suppressed if a done event already exists for these args, unless
        refresh=True (which forces re-emission for use with put --force).
        """
        if not vault.exists(_SEED_URI):
            return []
        profile_bytes = vault.load(_SEED_URI)
        profile_hash = hashlib.sha256(profile_bytes).hexdigest()[:16]
        args = {
            "profile_hash": profile_hash,
            "seed_uri": _SEED_URI,
            "refresh": False,
        }
        if not refresh and queue.is_done(self.name, self.version, args):
            return []
        return [Candidate(step=self.name, node_id=None, args=args)]

    async def work(self, args: dict, vault: Vault, log: Log) -> dict:  # type: ignore[type-arg]
        profile_path = vault.root / args["seed_uri"]
        refresh = bool(args.get("refresh", False))

        log(f"profile_hash={args['profile_hash']}  refresh={refresh}")
        rows = _pipeline_run(profile_path, refresh=refresh)
        log(f"pipeline returned {len(rows)} rows")

        jsonl_bytes = rows_to_jsonl_bytes(rows)
        uri = vault.store(None, self.name, "listing", "jsonl", jsonl_bytes)
        log(f"saved {len(jsonl_bytes)} bytes → {uri}")

        return {"listing_uri": uri, "count": len(rows)}
