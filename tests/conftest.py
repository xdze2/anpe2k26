import anpe.profile as profile_mod
import pytest


@pytest.fixture(autouse=True)
def _isolate_profile_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(profile_mod, "_USER_DATA_DIR", tmp_path)
