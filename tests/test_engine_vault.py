import pytest
from pathlib import Path
from anpe.engine.vault import Vault, VaultWriteError


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    return Vault(root=tmp_path)


def test_save_and_load_roundtrip(vault: Vault) -> None:
    uri = "node_abc/raw/2026-05-08T1200_homepage.html"
    data = b"<html>hello</html>"
    returned_uri = vault.save(uri, data)
    assert returned_uri == uri
    assert vault.load(uri) == data


def test_save_creates_parent_dirs(vault: Vault) -> None:
    uri = "node_abc/summarize/2026-05-08T1200_sum.json"
    vault.save(uri, b"{}")
    assert vault.exists(uri)


def test_write_once_raises_on_overwrite(vault: Vault) -> None:
    uri = "node_abc/raw/file.txt"
    vault.save(uri, b"original")
    with pytest.raises(VaultWriteError):
        vault.save(uri, b"overwrite")


def test_exists_false_before_save(vault: Vault) -> None:
    assert not vault.exists("node_abc/raw/missing.txt")


def test_exists_true_after_save(vault: Vault) -> None:
    uri = "node_abc/raw/present.txt"
    vault.save(uri, b"data")
    assert vault.exists(uri)


def test_load_missing_raises(vault: Vault) -> None:
    with pytest.raises(FileNotFoundError):
        vault.load("node_abc/raw/ghost.txt")
