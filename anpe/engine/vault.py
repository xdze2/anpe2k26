"""Write-once artifact store backed by the local filesystem.

URI convention: {node_id}/{step}/{timestamp}_{slug}.{ext}
Callers pass metadata; the vault builds and returns the opaque URI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

USER_VAULT_DIR = Path(__file__).parent.parent.parent / "user_vault"


class VaultWriteError(Exception):
    pass


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


class Vault:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else USER_VAULT_DIR

    def store(self, node_id: str, step: str, slug: str, ext: str, data: bytes) -> str:
        """Write data and return its opaque URI: {node_id}/{step}/{ts}_{slug}.{ext}."""
        uri = f"{node_id}/{step}/{_ts()}_{slug}.{ext}"
        path = self.root / uri
        if path.exists():
            raise VaultWriteError(f"vault is write-once: {uri!r} already exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return uri

    def load(self, uri: str) -> bytes:
        path = self.root / uri
        return path.read_bytes()

    def exists(self, uri: str) -> bool:
        return (self.root / uri).exists()
