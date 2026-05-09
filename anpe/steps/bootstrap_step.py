"""bootstrap step — scan user_profile.yaml, produce company listing JSONL in vault."""

from __future__ import annotations

import hashlib
from pathlib import Path

from anpe.steps.bootstrap.pipeline import rows_to_jsonl_bytes, run as _pipeline_run
from anpe.config import USER_DATA_DIR
from anpe.engine.queue import Queue
from anpe.steps import api_throttles
from anpe.engine.base import Candidate, Log
from anpe.engine.vault import Vault

_PROFILE_PATH = USER_DATA_DIR / "user_profile.yaml"
_NODE_ID = "_bootstrap"


class BootstrapStep:
    name = "bootstrap"
    version = "v2"
    description = "Hash user_profile.yaml and produce a company listing JSONL in the vault."
    rate_gate = api_throttles.NONE

    def scan(self, queue: Queue, _vault: Vault, refresh: bool = False, **_: object) -> list[Candidate]:
        """Emit one candidate keyed on the profile's content hash.

        Suppressed if a done event already exists for these args, unless
        refresh=True (which forces re-emission for use with put --force).
        """
        if not _PROFILE_PATH.exists():
            return []
        profile_hash = hashlib.sha256(_PROFILE_PATH.read_bytes()).hexdigest()[:16]
        args = {
            "profile_hash": profile_hash,
            "profile_path": str(_PROFILE_PATH),
            "refresh": False,
        }
        if not refresh and queue.is_done(self.name, self.version, args):
            return []
        return [Candidate(step=self.name, node_id=_NODE_ID, args=args)]

    async def work(self, args: dict, vault: Vault, log: Log) -> dict:  # type: ignore[type-arg]
        profile_path = Path(args["profile_path"])
        refresh = bool(args.get("refresh", False))

        log(f"profile_hash={args['profile_hash']}  refresh={refresh}")
        rows = _pipeline_run(profile_path, refresh=refresh)
        log(f"pipeline returned {len(rows)} rows")

        jsonl_bytes = rows_to_jsonl_bytes(rows)
        uri = vault.store(_NODE_ID, self.name, "listing", "jsonl", jsonl_bytes)
        log(f"saved {len(jsonl_bytes)} bytes → {uri}")

        return {"listing_uri": uri, "count": len(rows)}
