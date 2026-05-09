import pytest
from pathlib import Path
from anpe.engine.vault import Vault, VaultWriteError


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    return Vault(root=tmp_path)


# --- store() — vault-managed URI with timestamp ---

def test_store_returns_uri(vault: Vault) -> None:
    uri = vault.store("node_abc", "fetch_ddg", "uid123", "json", b'{"results":[]}')
    assert uri.startswith("fetch_ddg/node_abc/")
    assert uri.endswith("_uid123.json")


def test_store_data_is_loadable(vault: Vault) -> None:
    data = b'{"results":[]}'
    uri = vault.store("node_abc", "fetch_ddg", "uid123", "json", data)
    assert vault.load(uri) == data


def test_store_creates_parent_dirs(vault: Vault) -> None:
    uri = vault.store("node_abc", "fetch_ddg", "uid123", "json", b"{}")
    assert vault.exists(uri)


def test_store_uri_contains_step(vault: Vault) -> None:
    uri = vault.store("node_abc", "fetch_ddg", "uid123", "json", b"{}")
    parts = uri.split("/")
    assert parts[0] == "fetch_ddg"
    assert parts[1] == "node_abc"


# --- shared ---

def test_exists_false_before_store(vault: Vault) -> None:
    assert not vault.exists("bootstrap/20260101T000000_listing.jsonl")


def test_load_missing_raises(vault: Vault) -> None:
    with pytest.raises(FileNotFoundError):
        vault.load("node_abc/fetch_ddg/ghost.json")
