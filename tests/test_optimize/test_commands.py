"""Tests for optimize/commands.py — /optimize and /mode slash commands."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

import pytest

from anythink.app.chat import ChatState
from anythink.app.context import AppContext
from anythink.commands.registry import CommandRegistry
from anythink.config.manager import Paths
from anythink.optimize.commands import register_optimize_commands


@pytest.fixture()
def registry() -> CommandRegistry:
    r = CommandRegistry()
    register_optimize_commands(r)
    return r


@pytest.fixture()
def ctx(xdg_dirs: Paths) -> AppContext:
    return AppContext.create(paths=xdg_dirs, console_file=StringIO())


@pytest.fixture()
def state(ctx: AppContext) -> ChatState:
    provider = MagicMock()
    provider.name = "mock"
    return ChatState(provider=provider, model_id="test-model", context_window=8192)


# ── Registration ──────────────────────────────────────────────────────────────


class TestRegistration:
    def test_optimize_and_mode_registered(self, registry: CommandRegistry) -> None:
        names = set(registry.names())
        assert "optimize" in names
        assert "mode" in names

    def test_register_commands_includes_optimize(self, xdg_dirs: Paths) -> None:
        from anythink.commands.handlers import register_commands

        r = CommandRegistry()
        register_commands(r)
        assert "optimize" in r.names()
        assert "mode" in r.names()


# ── /mode ─────────────────────────────────────────────────────────────────────


class TestModeCommand:
    async def test_mode_online(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/mode online", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().mode == "online"
        assert result.action == "mmos_hud_update"

    async def test_mode_offline(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/mode offline", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().mode == "offline"

    async def test_mode_auto(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/mode auto", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().mode == "auto"

    async def test_mode_invalid_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/mode turbo", ctx, state)
        assert result.error is True
        assert "turbo" in result.message

    async def test_mode_empty_args_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/mode ", ctx, state)
        assert result.error is True


# ── /optimize (no args) ───────────────────────────────────────────────────────


class TestOptimizePanel:
    async def test_no_args_returns_panel_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize", ctx, state)
        assert result.action == "open_optimize_panel"
        assert result.error is False


# ── /optimize status ──────────────────────────────────────────────────────────


class TestOptimizeStatus:
    async def test_status_returns_message(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize status", ctx, state)
        assert result.error is False
        assert result.message is not None
        assert "Engine" in result.message
        assert "Mode" in result.message
        assert "Priority" in result.message

    async def test_status_shows_registry_count(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize status", ctx, state)
        assert "Registry" in result.message


# ── /optimize toggle ──────────────────────────────────────────────────────────


class TestOptimizeToggle:
    async def test_toggle_flips_enabled(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        initial = ctx.mmos_settings.get().enabled
        await registry.dispatch("/optimize toggle", ctx, state)
        assert ctx.mmos_settings.get().enabled is not initial

    async def test_toggle_twice_restores_original(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        initial = ctx.mmos_settings.get().enabled
        await registry.dispatch("/optimize toggle", ctx, state)
        await registry.dispatch("/optimize toggle", ctx, state)
        assert ctx.mmos_settings.get().enabled is initial

    async def test_toggle_returns_hud_update_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize toggle", ctx, state)
        assert result.action == "mmos_hud_update"


# ── /optimize priority ────────────────────────────────────────────────────────


class TestOptimizePriority:
    async def test_set_quality(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize priority quality", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().priority == "quality"

    async def test_set_reliability(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize priority reliability", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().priority == "reliability"

    async def test_set_hybrid(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize priority hybrid", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().priority == "hybrid"

    async def test_invalid_priority_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize priority turbo", ctx, state)
        assert result.error is True

    async def test_no_arg_shows_current(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize priority", ctx, state)
        assert result.error is False
        assert result.message is not None


# ── /optimize microprompt ─────────────────────────────────────────────────────


class TestOptimizeMicroprompt:
    async def test_microprompt_toggles(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        initial = ctx.mmos_settings.get().microprompt_enabled
        await registry.dispatch("/optimize microprompt", ctx, state)
        assert ctx.mmos_settings.get().microprompt_enabled is not initial

    async def test_microprompt_toggle_twice_restores(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        initial = ctx.mmos_settings.get().microprompt_enabled
        await registry.dispatch("/optimize microprompt", ctx, state)
        await registry.dispatch("/optimize microprompt", ctx, state)
        assert ctx.mmos_settings.get().microprompt_enabled is initial

    async def test_microprompt_returns_hud_update(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize microprompt", ctx, state)
        assert result.action == "mmos_hud_update"


# ── /optimize plan ────────────────────────────────────────────────────────────


class TestOptimizePlan:
    async def test_plan_off(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize plan off", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().plan_mode_enabled is False

    async def test_plan_on(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        await registry.dispatch("/optimize plan off", ctx, state)
        result = await registry.dispatch("/optimize plan on", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().plan_mode_enabled is True

    async def test_plan_approval_on(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize plan approval on", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().plan_approval_required is True

    async def test_plan_approval_off(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize plan approval off", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().plan_approval_required is False

    async def test_plan_invalid_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize plan maybe", ctx, state)
        assert result.error is True

    async def test_plan_no_arg_shows_current(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize plan", ctx, state)
        assert result.error is False


# ── /optimize ensemble ────────────────────────────────────────────────────────


class TestOptimizeEnsemble:
    async def test_set_mixing_mode(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize ensemble chaining", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().mixing_mode == "chaining"

    async def test_set_count(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize ensemble count 3", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().ensemble_count == 3

    async def test_count_out_of_range_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize ensemble count 10", ctx, state)
        assert result.error is True

    async def test_invalid_mode_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize ensemble broadcast", ctx, state)
        assert result.error is True


# ── /optimize history ─────────────────────────────────────────────────────────


class TestOptimizeHistory:
    async def test_set_history_mode_semantic(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize history semantic", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().history_mode == "semantic"

    async def test_set_history_mode_recency(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize history recency", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().history_mode == "recency"

    async def test_set_history_max_tokens(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize history max 4096", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().history_max_tokens == 4096

    async def test_history_max_below_minimum_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize history max 10", ctx, state)
        assert result.error is True

    async def test_invalid_history_mode_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize history future", ctx, state)
        assert result.error is True


# ── /optimize ratelimit ───────────────────────────────────────────────────────


class TestOptimizeRatelimit:
    async def test_ratelimit_returns_panel_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize ratelimit", ctx, state)
        assert result.action == "open_ratelimit_panel"
        assert result.error is False


# ── /optimize reset ───────────────────────────────────────────────────────────


class TestOptimizeReset:
    async def test_reset_returns_confirm_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize reset", ctx, state)
        assert result.action == "optimize_reset_confirm"
        assert result.error is False


# ── /optimize registry ────────────────────────────────────────────────────────


class TestOptimizeRegistry:
    async def test_registry_no_args_returns_panel_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize registry", ctx, state)
        assert result.action == "open_optimize_registry"

    async def test_registry_add_returns_add_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize registry add", ctx, state)
        assert result.action == "open_optimize_registry_add"

    async def test_registry_edit_returns_edit_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch(
            "/optimize registry edit groq/llama3-70b-8192", ctx, state
        )
        assert result.action == "open_optimize_registry_edit"
        assert result.extra.get("model_id") == "groq/llama3-70b-8192"

    async def test_registry_edit_no_id_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize registry edit", ctx, state)
        assert result.error is True

    async def test_registry_delete_nonexistent_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch(
            "/optimize registry delete nonexistent/ghost", ctx, state
        )
        assert result.error is True
        assert "not found" in result.message.lower()

    async def test_registry_delete_user_entry(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from anythink.optimize.models import ModelCapability

        cap = ModelCapability(
            id="custom/test-delete",
            provider="custom",
            display_name="Test",
            tier="local",
            context_window=4096,
            max_output_tokens=2048,
            rpm_limit=None,
            tpm_limit=None,
            rpd_limit=None,
            strength_categories=["coding"],
            speed_class="fast",
            quality_class="medium",
            supports_system_prompt=True,
            supports_streaming=True,
            requires_network=False,
        )
        ctx.mmos_registry.add_user_entry(cap)
        assert ctx.mmos_registry.get("custom/test-delete") is not None

        result = await registry.dispatch(
            "/optimize registry delete custom/test-delete", ctx, state
        )
        assert result.error is False
        assert ctx.mmos_registry.get("custom/test-delete") is None

    async def test_registry_export_creates_file(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize registry export", ctx, state)
        assert result.error is False
        assert "exported" in result.message.lower()

    async def test_registry_import_missing_file_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch(
            "/optimize registry import /nonexistent/path/registry.json", ctx, state
        )
        assert result.error is True

    async def test_registry_unknown_subcommand_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize registry frobnicate", ctx, state)
        assert result.error is True


# ── /optimize routing ─────────────────────────────────────────────────────────


class TestOptimizeRouting:
    async def test_set_routing_strategy(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize routing combined", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().routing_strategy == "combined"

    async def test_invalid_routing_strategy_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize routing fuzzy", ctx, state)
        assert result.error is True

    async def test_no_arg_shows_current(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize routing", ctx, state)
        assert result.error is False


# ── /optimize mode alias ──────────────────────────────────────────────────────


class TestOptimizeModeAlias:
    async def test_optimize_mode_delegates_to_mode_handler(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize mode offline", ctx, state)
        assert result.error is False
        assert ctx.mmos_settings.get().mode == "offline"


# ── /optimize help ────────────────────────────────────────────────────────────


class TestOptimizeHelp:
    async def test_help_lists_subcommands(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize help", ctx, state)
        assert result.error is False
        assert "toggle" in result.message
        assert "priority" in result.message
        assert "ratelimit" in result.message

    async def test_unknown_subcommand_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/optimize frobnicate", ctx, state)
        assert result.error is True


# ── Settings persistence ──────────────────────────────────────────────────────


class TestSettingsPersistence:
    async def test_mode_change_persists_across_manager_reload(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState, xdg_dirs: Paths
    ) -> None:
        await registry.dispatch("/mode offline", ctx, state)

        # Simulate reloading from disk
        from anythink.optimize.settings_manager import OptimizeSettingsManager

        fresh = OptimizeSettingsManager(path=xdg_dirs.optimize_settings_file)
        assert fresh.get().mode == "offline"

    async def test_priority_persists_across_manager_reload(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState, xdg_dirs: Paths
    ) -> None:
        await registry.dispatch("/optimize priority hybrid", ctx, state)

        from anythink.optimize.settings_manager import OptimizeSettingsManager

        fresh = OptimizeSettingsManager(path=xdg_dirs.optimize_settings_file)
        assert fresh.get().priority == "hybrid"
