"""bootstrap step — scan seed_query.yaml, produce listing.jsonl in vault root."""

from __future__ import annotations

from collections.abc import Iterator

from anpe.engine.types import Candidate, Log
from anpe.engine.vault import Vault
from anpe.steps.bootstrap.pipeline import rows_to_jsonl_bytes, run as _pipeline_run

_SEED_URI = "seed_query.yaml"
_OUTPUT_URI = "listing.jsonl"


class BootstrapStep:
    name = "bootstrap"

    def scan(self, vault: Vault, overwrite: bool = False, **_: object) -> Iterator[Candidate]:
        if not vault.exists(_SEED_URI):
            return
        if not overwrite and vault.exists(_OUTPUT_URI):
            return
        yield Candidate(node_id=None, args={"seed_uri": _SEED_URI})

    def work(self, args: dict, vault: Vault, log: Log) -> None:  # type: ignore[type-arg]
        profile_path = vault.root / args["seed_uri"]
        rows = _pipeline_run(profile_path)
        log(f"pipeline returned {len(rows)} rows")
        jsonl_bytes = rows_to_jsonl_bytes(rows)
        out_path = vault.root / _OUTPUT_URI
        out_path.write_bytes(jsonl_bytes)
        log(f"saved {len(jsonl_bytes)} bytes → {_OUTPUT_URI}")
