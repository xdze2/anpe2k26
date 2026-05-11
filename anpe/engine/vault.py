"""Write-once artifact store backed by the local filesystem."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anpe.engine.types import Log

USER_VAULT_DIR = Path(__file__).parent.parent.parent / "user_vault"


class VaultWriteError(Exception):
    pass


class Vault:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else USER_VAULT_DIR

    def write(self, uri: str, data: bytes, log: "Log | None" = None) -> None:
        """Write data to uri (relative to vault root). Overwrites if already exists."""
        path = self.root / uri
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        msg = f"wrote {len(data)} bytes → {uri}"
        print(msg)
        if log is not None:
            log(msg)

    def load(self, uri: str) -> bytes:
        path = self.root / uri
        return path.read_bytes()

    def exists(self, uri: str) -> bool:
        return (self.root / uri).exists()

    def output_uri(self, node_id: str, step_name: str) -> str:
        """Return the canonical output path for a node/step pair."""
        return f"nodes/{node_id}/{step_name}_{node_id[:8]}.json"
