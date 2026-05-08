"""Write-once artifact store backed by the local filesystem.

URI convention: {node_id}/{stage}/{timestamp}_{slug}.{ext}
Maps directly to user_vault/{uri} on disk.
"""

from __future__ import annotations

from pathlib import Path

USER_VAULT_DIR = Path(__file__).parent.parent.parent / "user_vault"


class VaultWriteError(Exception):
    pass


class Vault:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or USER_VAULT_DIR

    def save(self, uri: str, data: bytes) -> str:
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
