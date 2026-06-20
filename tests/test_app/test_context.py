"""Tests for app/context.py."""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from anythink.app.context import AppContext
from anythink.config.manager import ConfigManager, Paths
from anythink.config.models import ModelRegistry
from anythink.config.personas import PersonaManager
from anythink.config.schema import AppConfig
from anythink.keys.manager import KeyManager
from anythink.plugins.manager import PluginManager
from anythink.providers.registry import ProviderRegistry
from anythink.search.registry import SearchRegistry
from anythink.session.manager import SessionManager


@pytest.fixture()
def ctx(xdg_dirs: Paths) -> AppContext:
    return AppContext.create(paths=xdg_dirs, console_file=StringIO())


class TestAppContextCreate:
    def test_returns_app_context_instance(self, ctx: AppContext) -> None:
        assert isinstance(ctx, AppContext)

    def test_config_is_app_config(self, ctx: AppContext) -> None:
        assert isinstance(ctx.config, AppConfig)

    def test_default_theme_is_midnight(self, ctx: AppContext) -> None:
        assert ctx.theme.name == "midnight"

    def test_console_is_console_instance(self, ctx: AppContext) -> None:
        assert isinstance(ctx.console, Console)

    def test_key_manager_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.key_manager, KeyManager)

    def test_provider_registry_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.provider_registry, ProviderRegistry)

    def test_model_registry_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.model_registry, ModelRegistry)

    def test_persona_manager_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.persona_manager, PersonaManager)

    def test_session_manager_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.session_manager, SessionManager)

    def test_search_registry_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.search_registry, SearchRegistry)

    def test_plugin_manager_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.plugin_manager, PluginManager)

    def test_config_manager_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.config_manager, ConfigManager)

    def test_paths_set(self, ctx: AppContext, xdg_dirs: Paths) -> None:
        assert ctx.paths == xdg_dirs

    def test_theme_matches_config_active_theme(self, xdg_dirs: Paths) -> None:
        xdg_dirs.config_file.write_text("active_theme: aurora\n")
        ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
        assert ctx.theme.name == "aurora"

    def test_console_file_captured(self, xdg_dirs: Paths) -> None:
        buf = StringIO()
        ctx = AppContext.create(paths=xdg_dirs, console_file=buf)
        ctx.console.print("hello")
        assert "hello" in buf.getvalue()

    def test_create_without_paths_uses_xdg_resolution(
        self, monkeypatch: pytest.MonkeyPatch, xdg_dirs: Paths
    ) -> None:
        # xdg_dirs fixture already set XDG env vars — create() without paths should use them
        ctx = AppContext.create(console_file=StringIO())
        assert ctx.paths.config_dir == xdg_dirs.config_dir
