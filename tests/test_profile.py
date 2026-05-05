"""Tests for anpe/profile.py."""

import pytest
from pathlib import Path

import anpe.profile as profile_mod


@pytest.fixture(autouse=True)
def patch_profile_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(profile_mod, "_USER_DATA_DIR", tmp_path)


def test_active_profile_file_none_when_empty(tmp_path):
    assert profile_mod.active_profile_file() is None


def test_active_profile_file_returns_most_recent(tmp_path):
    (tmp_path / "profile_20260505T1200.md").write_text("old")
    (tmp_path / "profile_20260506T0900.md").write_text("new")
    (tmp_path / "profile_20260504T0800.md").write_text("oldest")

    result = profile_mod.active_profile_file()
    assert result.name == "profile_20260506T0900.md"


def test_read_profile_empty_when_no_file():
    assert profile_mod.read_profile() == ""


def test_read_profile_returns_active(tmp_path):
    (tmp_path / "profile_20260505T1200.md").write_text("old profile\n")
    (tmp_path / "profile_20260506T0900.md").write_text("new profile\n")

    assert profile_mod.read_profile() == "new profile"


def test_write_profile_snapshot_creates_file(tmp_path):
    path, warning = profile_mod.write_profile_snapshot("# My profile\n\nLooking for PME.")
    assert path.exists()
    assert path.name.startswith("profile_")
    assert path.suffix == ".md"
    assert warning == ""


def test_write_profile_snapshot_is_active_after_write(tmp_path):
    profile_mod.write_profile_snapshot("first")
    profile_mod.write_profile_snapshot("second")

    assert profile_mod.read_profile() == "second"


def test_write_profile_snapshot_warns_when_too_long(tmp_path):
    long_content = " ".join(["word"] * 401)
    _, warning = profile_mod.write_profile_snapshot(long_content)
    assert "Warning" in warning
    assert "401" in warning


def test_write_profile_snapshot_no_warning_at_limit(tmp_path):
    content = " ".join(["word"] * 400)
    _, warning = profile_mod.write_profile_snapshot(content)
    assert warning == ""
