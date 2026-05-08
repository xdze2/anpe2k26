"""fetch_ddg step — scan bootstrap listing + pending follow-up targets, run DDG search."""

from __future__ import annotations

import json

from anpe.engine.steps.base import Candidate, Log
from anpe.engine.vault import USER_VAULT_DIR, Vault
from anpe.node_dir import NODES_DIR
from anpe.prospect.errors import FetchBlockedError, FetchNotFoundError, FetchRetryableError
from anpe.prospect.registry import FETCH_TOOLS
from anpe.prospect.seed import node_id_for

_TOOL = "ddg"
_BOOTSTRAP_NODE = "_bootstrap"


class FetchDdgStep:
    name = "fetch_ddg"
    version = "v1"

    def scan(self, count: int = 10, **_: object) -> list[Candidate]:
        """Return Candidates from two sources:
        1. Bootstrap listing — new companies not yet in NODES_DIR (capped at count).
        2. Existing fetch.jsonl entries with pending DDG targets (follow-ups, uncapped).
        """
        candidates: list[Candidate] = []
        candidates.extend(self._scan_listing(count))
        candidates.extend(self._scan_followups())
        return candidates

    def _scan_listing(self, count: int) -> list[Candidate]:
        """Read the latest bootstrap listing JSONL, emit one Candidate per new company."""
        listing_files = sorted(USER_VAULT_DIR.glob(f"{_BOOTSTRAP_NODE}/bootstrap/*_listing.jsonl"))
        if not listing_files:
            return []
        listing_path = listing_files[-1]

        existing_nodes: set[str] = set()
        if NODES_DIR.exists():
            existing_nodes = {p.name for p in NODES_DIR.iterdir() if p.is_dir()}

        # also skip nodes already in the vault
        vault_nodes: set[str] = set()
        if USER_VAULT_DIR.exists():
            vault_nodes = {
                p.name for p in USER_VAULT_DIR.iterdir()
                if p.is_dir() and not p.name.startswith("_")
            }

        seen = existing_nodes | vault_nodes
        candidates: list[Candidate] = []
        for line in listing_path.read_text(encoding="utf-8").splitlines():
            if len(candidates) >= count:
                break
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            node_id = node_id_for(row["nom_complet"], row["siren"])
            if node_id in seen:
                continue
            seen.add(node_id)
            candidates.append(Candidate(
                step=self.name,
                node_id=node_id,
                args={
                    "node_id": node_id,
                    "tool": _TOOL,
                    "target": row["nom_complet"],
                    "source": "listing",
                    "listing_uri": str(listing_path.relative_to(USER_VAULT_DIR)),
                },
                context={"nom_complet": row["nom_complet"], "siren": row["siren"]},
            ))
        return candidates

    def _scan_followups(self) -> list[Candidate]:
        """Return one Candidate per pending DDG target in existing fetch.jsonl files."""
        if not NODES_DIR.exists():
            return []

        candidates: list[Candidate] = []
        for node_path in sorted(NODES_DIR.iterdir()):
            if not node_path.is_dir():
                continue
            node_id = node_path.name
            fetch_file = node_path / "fetch.jsonl"
            if not fetch_file.exists():
                continue

            events = [
                json.loads(line)
                for line in fetch_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            puts: dict[str, dict] = {}  # type: ignore[type-arg]
            latest: dict[str, dict] = {}  # type: ignore[type-arg]
            for ev in events:
                uid = ev.get("uid", "")
                if ev["event"] == "put":
                    puts[uid] = ev
                latest[uid] = ev

            for uid, put_ev in puts.items():
                if put_ev.get("tool") != _TOOL:
                    continue
                last = latest.get(uid, put_ev)
                if last["event"] not in ("put", "summarize_error", "resummarize"):
                    continue
                candidates.append(Candidate(
                    step=self.name,
                    node_id=node_id,
                    args={
                        "node_id": node_id,
                        "uid": uid,
                        "tool": _TOOL,
                        "target": put_ev["target"],
                        "source": "followup",
                    },
                    context={"last_event": last["event"]},
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
        uid = args.get("uid", node_id[:8])
        uri = vault.store(node_id, self.name, uid, fetch_tool.raw_ext, raw_data.encode())
        log(f"saved → {uri}")
        return {"raw_uri": uri, "tool": _TOOL, "target": target}
