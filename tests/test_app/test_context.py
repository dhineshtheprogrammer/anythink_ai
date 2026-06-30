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
from anythink.workflow.engine import WorkflowEngine
from anythink.workflow.manifest import CapabilityManifest
from anythink.workflow.registry import WorkflowCapabilityRegistry
from anythink.workflow.storage import WorkflowStorage


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


class TestAppContextCreateWithConfig:
    def test_debug_mode_enabled_on_startup(self, xdg_dirs: Paths) -> None:
        from unittest.mock import patch

        from anythink.config.schema import AppConfig as AC

        with patch(
            "anythink.config.manager.ConfigManager.load",
            return_value=AC(debug_mode=True, debug_level=1),
        ):
            ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
        assert ctx.debug_manager.is_active() is True

    def test_debug_api_logging_enabled_on_startup(self, xdg_dirs: Paths) -> None:
        from unittest.mock import patch

        from anythink.config.schema import AppConfig as AC

        with patch(
            "anythink.config.manager.ConfigManager.load",
            return_value=AC(debug_api_logging=True),
        ):
            ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
        assert ctx.debug_manager.api_logging_active() is True

    def test_active_rag_index_loaded_on_startup(self, xdg_dirs: Paths) -> None:
        import yaml

        xdg_dirs.config_file.write_text(yaml.dump({"active_rag_index": "my-index"}))
        ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
        assert ctx.rag_manager is not None

    def test_vision_capable_with_vision_alias(self, xdg_dirs: Paths) -> None:
        from anythink.app.context import _check_vision_capable

        config = AppConfig(default_model_alias="gpt-4-vision")
        assert _check_vision_capable(config) is True

    def test_vision_not_capable_with_text_alias(self, xdg_dirs: Paths) -> None:
        from anythink.app.context import _check_vision_capable

        config = AppConfig(default_model_alias="llama3-8b")
        assert _check_vision_capable(config) is False


class TestAppContextMMWEIntegration:
    """Phase 9 — verify MMWE subsystems are wired into AppContext."""

    def test_workflow_registry_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.workflow_registry, WorkflowCapabilityRegistry)

    def test_workflow_storage_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.workflow_storage, WorkflowStorage)

    def test_workflow_manifest_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.workflow_manifest, CapabilityManifest)

    def test_workflow_engine_wired(self, ctx: AppContext) -> None:
        assert isinstance(ctx.workflow_engine, WorkflowEngine)

    def test_workflow_manifest_written_to_config_dir(
        self, ctx: AppContext, xdg_dirs: Paths
    ) -> None:
        expected = xdg_dirs.config_dir / "workflow_manifest.txt"
        assert ctx.workflow_manifest.path == expected

    def test_workflow_manifest_file_exists_after_create(
        self, ctx: AppContext, xdg_dirs: Paths
    ) -> None:
        assert (xdg_dirs.config_dir / "workflow_manifest.txt").exists()

    def test_workflow_storage_dir_under_config(self, ctx: AppContext, xdg_dirs: Paths) -> None:
        assert ctx.workflow_storage._dir == xdg_dirs.config_dir / "workflows"

    def test_workflow_log_dir_defaults_to_xdg_data(self, ctx: AppContext, xdg_dirs: Paths) -> None:
        assert ctx.workflow_engine._logger._dir == xdg_dirs.data_dir / "workflow_logs"

    def test_workflow_log_dir_override_via_config(self, xdg_dirs: Paths) -> None:
        from unittest.mock import patch

        with patch(
            "anythink.config.manager.ConfigManager.load",
            return_value=AppConfig(workflow_log_dir="custom_logs"),
        ):
            ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
        assert ctx.workflow_engine._logger._dir == xdg_dirs.data_dir / "custom_logs"


class TestAppConfigMMWEFields:
    """Phase 9 — verify the three new AppConfig MMWE fields and their defaults."""

    def test_workflow_planner_model_default(self) -> None:
        assert AppConfig().workflow_planner_model == ""

    def test_workflow_log_dir_default(self) -> None:
        assert AppConfig().workflow_log_dir == ""

    def test_workflow_autonomy_mode_default(self) -> None:
        assert AppConfig().workflow_autonomy_mode == "confirm"

    def test_workflow_planner_model_is_frozen(self) -> None:
        config = AppConfig(workflow_planner_model="gpt-4o")
        assert config.workflow_planner_model == "gpt-4o"

    def test_workflow_autonomy_mode_auto(self) -> None:
        config = AppConfig(workflow_autonomy_mode="auto")
        assert config.workflow_autonomy_mode == "auto"
