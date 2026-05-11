"""Write-once artifact store backed by the local filesystem.

URI convention: {step}/{node_id}/{timestamp}_{slug}.{ext}
For process-level steps with no node, node_id is omitted: {step}/{timestamp}_{slug}.{ext}
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

    def store(self, node_id: str | None, step: str, slug: str, ext: str, data: bytes) -> str:
        """Write data and return its opaque URI: {step}/{node_id}/{ts}_{slug}.{ext}.

        When node_id is None (process-level step), the URI is {step}/{ts}_{slug}.{ext}.
        """
        if node_id is not None:
            uri = f"{step}/{node_id}/{_ts()}_{slug}.{ext}"
        else:
            uri = f"{step}/{_ts()}_{slug}.{ext}"
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

    def output_uri(self, node_id: str, step_name: str) -> str:
        """Return the canonical output path for a node/step pair."""
        return f"nodes/{node_id}/{step_name}_{node_id[:8]}.json"
