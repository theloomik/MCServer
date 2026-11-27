"""Tests for the servers folder location shared with the legacy application."""

from pathlib import Path

import pytest

from mcserver.presentation.paths import servers_root


def test_packaged_app_uses_local_app_data(tmp_path: Path) -> None:
    root = servers_root(frozen=True, environ={"LOCALAPPDATA": str(tmp_path / "Local")})

    assert root == (tmp_path / "Local" / "MCServer" / "servers").resolve()


def test_packaged_app_falls_back_to_home_app_data(tmp_path: Path) -> None:
    root = servers_root(frozen=True, environ={}, home=tmp_path)

    assert root == (tmp_path / "AppData" / "Local" / "MCServer" / "servers").resolve()


def test_development_run_uses_minecraft_servers_in_working_directory(tmp_path: Path) -> None:
    assert servers_root(frozen=False, cwd=tmp_path) == (tmp_path / "minecraft_servers").resolve()


def test_matches_legacy_server_manager_in_development(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards against drift: the legacy manager is the source of truth for the folder."""
    monkeypatch.chdir(tmp_path)
    import core

    legacy_root = core.ServerManager().servers_dir

    assert servers_root(frozen=False) == legacy_root


def test_does_not_create_the_folder(tmp_path: Path) -> None:
    servers_root(frozen=False, cwd=tmp_path)

    assert not (tmp_path / "minecraft_servers").exists()
