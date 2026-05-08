"""fetch_ddg step — scan pending DDG targets, work runs the DDG search."""

from __future__ import annotations

import json

from anpe.engine.steps.base import Candidate, Log
from anpe.engine.vault import Vault
from anpe.node_dir import NODES_DIR
from anpe.prospect.errors import FetchBlockedError, FetchNotFoundError, FetchRetryableError
from anpe.prospect.registry import FETCH_TOOLS

_TOOL = "ddg"


class FetchDdgStep:
    name = "fetch_ddg"
    version = "v1"

    def scan(self, **_: object) -> list[Candidate]:
        """Return one Candidate per pending DDG target across all nodes."""
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
                    args={"uid": uid, "tool": _TOOL, "target": put_ev["target"]},
                    context={"last_event": last["event"]},
                ))

        return candidates

    async def work(self, args: dict, vault: Vault, log: Log) -> dict:  # type: ignore[type-arg]
        target = args["target"]
        fetch_tool = FETCH_TOOLS[_TOOL]

        log(f"fetching [{_TOOL}] {target}")
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
        uri = f"{args['node_id']}/raw/{args['uid']}_{_TOOL}.{fetch_tool.raw_ext}"
        vault.save(uri, raw_data.encode())
        log(f"saved → {uri}")
        return {"raw_uri": uri, "tool": _TOOL, "target": target}
