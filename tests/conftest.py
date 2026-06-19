"""Shared test fixtures for Anythink tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from anythink.config.manager import ConfigManager, Paths


@pytest.fixture()
def xdg_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Paths:
    """Redirect all XDG base dirs to a temp directory so tests never touch ~/.config."""
    config_home = tmp_path / "config"
    data_home = tmp_path / "data"
    state_home = tmp_path / "state"
    cache_home = tmp_path / "cache"

    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))

    paths = Paths(
        config_dir=config_home / "anythink",
        data_dir=data_home / "anythink",
        state_dir=state_home / "anythink",
        cache_dir=cache_home / "anythink",
    )
    paths.ensure_dirs()
    return paths


@pytest.fixture()
def config_manager(xdg_dirs: Paths) -> ConfigManager:
    """Return a ConfigManager pointed at the temp XDG dirs."""
    return ConfigManager(paths=xdg_dirs)
