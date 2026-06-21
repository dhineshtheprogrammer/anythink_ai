"""End-to-end tests for V3 slash command handlers.

Tests dispatch each new command through the full registry pipeline and verify
the CommandResult structure, confirming handlers are wired and execute correctly.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.app.chat import ChatState
from anythink.app.context import AppContext
from anythink.commands.handlers import register_commands
from anythink.commands.registry import CommandRegistry
from anythink.config.manager import Paths
from anythink.config.models import ModelAlias
from anythink.config.templates import PromptTemplate
from anythink.providers.base import TokenUsage

# ── shared fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def registry() -> CommandRegistry:
    r = CommandRegistry()
    register_commands(r)
    return r


@pytest.fixture()
def ctx(xdg_dirs: Paths) -> AppContext:
    return AppContext.create(paths=xdg_dirs, console_file=StringIO())


@pytest.fixture()
def state(ctx: AppContext) -> ChatState:
    provider = MagicMock()
    provider.name = "mock"
    return ChatState(provider=provider, model_id="mock-model", context_window=8192)


def _add_alias(ctx: AppContext, alias: str = "my-model") -> None:
    from dataclasses import replace

    ctx.model_registry.add(
        ModelAlias(alias=alias, provider="openai", model_id="gpt-4o", context_window=128000)
    )
    ctx.config = replace(ctx.config, default_model_alias=alias)


# ── /params ────────────────────────────────────────────────────────────────────


class TestParamsCommand:
    async def test_no_default_alias_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/params", ctx, state)
        assert result.error

    async def test_show_defaults_when_no_params_set(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        _add_alias(ctx)
        result = await registry.dispatch("/params", ctx, state)
        assert not result.error
        assert "provider defaults" in (result.message or "")

    async def test_set_temperature(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        _add_alias(ctx)
        result = await registry.dispatch("/params temperature=0.3", ctx, state)
        assert not result.error
        alias = ctx.model_registry.get("my-model")
        assert alias is not None
        assert alias.gen_params is not None
        assert alias.gen_params.temperature == pytest.approx(0.3)

    async def test_set_multiple_params(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        _add_alias(ctx)
        result = await registry.dispatch(
            "/params temperature=0.5 max_tokens=1024 top_p=0.9", ctx, state
        )
        assert not result.error
        alias = ctx.model_registry.get("my-model")
        assert alias is not None
        assert alias.gen_params is not None
        assert alias.gen_params.max_tokens == 1024
        assert alias.gen_params.top_p == pytest.approx(0.9)

    async def test_reset_clears_params(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        _add_alias(ctx)
        await registry.dispatch("/params temperature=0.1", ctx, state)
        result = await registry.dispatch("/params reset", ctx, state)
        assert not result.error
        alias = ctx.model_registry.get("my-model")
        assert alias is not None
        assert alias.gen_params is None

    async def test_invalid_value_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        _add_alias(ctx)
        result = await registry.dispatch("/params temperature=not-a-number", ctx, state)
        assert result.error

    async def test_unknown_param_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        _add_alias(ctx)
        result = await registry.dispatch("/params nonexistent=0.5", ctx, state)
        assert result.error


# ── /cost ──────────────────────────────────────────────────────────────────────


class TestCostCommand:
    async def test_session_cost_empty(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/cost", ctx, state)
        assert not result.error
        assert "$" in (result.message or "")

    async def test_cost_session_after_recording(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        ctx.spend_tracker.record(state.session_id, "gpt-4o", "openai", usage, cost_usd=0.0150)
        result = await registry.dispatch("/cost session", ctx, state)
        assert not result.error
        assert "0.0150" in (result.message or "")

    async def test_cost_today(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/cost today", ctx, state)
        assert not result.error

    async def test_cost_month(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/cost month", ctx, state)
        assert not result.error

    async def test_cost_by_model(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        ctx.spend_tracker.record(state.session_id, "gpt-4o", "openai", usage, 0.001)
        result = await registry.dispatch("/cost by-model", ctx, state)
        assert not result.error
        assert "gpt-4o" in (result.message or "")

    async def test_cost_by_provider(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        ctx.spend_tracker.record(state.session_id, "gpt-4o", "openai", usage, 0.001)
        result = await registry.dispatch("/cost by-provider", ctx, state)
        assert not result.error
        assert "openai" in (result.message or "")

    async def test_unknown_subcommand_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/cost badsubcmd", ctx, state)
        assert result.error


# ── /template ─────────────────────────────────────────────────────────────────


class TestTemplateCommand:
    async def test_list_empty(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/template list", ctx, state)
        assert not result.error
        assert "No templates" in (result.message or "")

    async def test_save_and_list(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        await registry.dispatch("/template save mytempl Review {{lang}} code.", ctx, state)
        result = await registry.dispatch("/template list", ctx, state)
        assert not result.error
        assert "mytempl" in (result.message or "")

    async def test_show_template(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.template_manager.add(PromptTemplate("t1", "Body {{x}}."))
        result = await registry.dispatch("/template show t1", ctx, state)
        assert not result.error
        assert "Body {{x}}." in (result.message or "")

    async def test_show_missing_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/template show nonexistent", ctx, state)
        assert result.error

    async def test_delete_template(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.template_manager.add(PromptTemplate("del-me", "body"))
        result = await registry.dispatch("/template delete del-me", ctx, state)
        assert not result.error
        assert not ctx.template_manager.exists("del-me")

    async def test_delete_missing_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/template delete missing", ctx, state)
        assert result.error

    async def test_save_shows_variables(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch(
            "/template save code-rev Review {{lang}} for {{issue}}.", ctx, state
        )
        assert not result.error
        assert "lang" in (result.message or "") or "variables" in (result.message or "")


# ── /use ──────────────────────────────────────────────────────────────────────


class TestUseCommand:
    async def test_use_missing_template_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/use nonexistent", ctx, state)
        assert result.error

    async def test_use_no_args_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/use", ctx, state)
        assert result.error

    async def test_use_renders_and_signals_send(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.template_manager.add(PromptTemplate("greet", "Hello {{name}}!"))
        result = await registry.dispatch("/use greet name=Alice", ctx, state)
        assert not result.error
        assert result.action == "template_send"
        assert result.extra.get("rendered") == "Hello Alice!"

    async def test_use_with_missing_variable_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.template_manager.add(PromptTemplate("twovar", "{{a}} and {{b}}."))
        result = await registry.dispatch("/use twovar a=x", ctx, state)
        assert result.error


# ── /doctor ───────────────────────────────────────────────────────────────────


class TestDoctorCommand:
    async def test_doctor_returns_report(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/doctor", ctx, state)
        assert not result.error
        msg = result.message or ""
        assert "Summary" in msg
        assert "passed" in msg

    async def test_doctor_contains_python_check(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/doctor", ctx, state)
        assert "Python" in (result.message or "")


# ── /update ───────────────────────────────────────────────────────────────────


class TestUpdateCommand:
    async def test_update_check_when_up_to_date(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from anythink import __version__

        with patch(
            "anythink.updater.fetch_latest_version", new=AsyncMock(return_value=__version__)
        ):
            result = await registry.dispatch("/update check", ctx, state)
        assert not result.error
        assert "up to date" in (result.message or "").lower()

    async def test_update_check_when_newer_available(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        with patch("anythink.updater.fetch_latest_version", new=AsyncMock(return_value="9.9.9")):
            result = await registry.dispatch("/update check", ctx, state)
        assert not result.error
        assert "9.9.9" in (result.message or "")

    async def test_update_check_no_network(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        with patch("anythink.updater.fetch_latest_version", new=AsyncMock(return_value=None)):
            result = await registry.dispatch("/update check", ctx, state)
        assert not result.error
        assert "PyPI" in (result.message or "")

    async def test_update_offers_upgrade_when_newer(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        with patch("anythink.updater.fetch_latest_version", new=AsyncMock(return_value="2.0.0")):
            with patch("anythink.updater.current_version", return_value="1.0.0"):
                result = await registry.dispatch("/update", ctx, state)
        assert not result.error
        assert result.action == "update_confirm"
        assert result.extra.get("latest") == "2.0.0"

    async def test_update_no_op_when_current(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        with patch("anythink.updater.fetch_latest_version", new=AsyncMock(return_value="1.0.0")):
            with patch("anythink.updater.current_version", return_value="1.0.0"):
                result = await registry.dispatch("/update", ctx, state)
        assert not result.error
        assert result.action != "update_confirm"


# ── /config ───────────────────────────────────────────────────────────────────


class TestConfigCommand:
    async def test_config_export_creates_file(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState, tmp_path: Path
    ) -> None:
        out = tmp_path / "backup.json"
        result = await registry.dispatch(f"/config export {out}", ctx, state)
        assert not result.error
        assert out.exists()

    async def test_config_export_no_path_uses_default(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/config export", ctx, state)
        assert not result.error
        assert "Exported" in (result.message or "") or "exported" in (result.message or "")

    async def test_config_import_nonexistent_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/config import /nonexistent/path.json", ctx, state)
        assert result.error

    async def test_config_no_subcommand_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/config", ctx, state)
        assert result.error


# ── /export ───────────────────────────────────────────────────────────────────


class TestExportCommand:
    async def test_export_markdown(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history.append(
            __import__("anythink.providers.base", fromlist=["ChatMessage"]).ChatMessage(
                role="user", content="Hello"
            )
        )
        result = await registry.dispatch("/export markdown", ctx, state)
        assert not result.error
        msg = result.message or ""
        assert ".md" in msg

    async def test_export_json(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/export json", ctx, state)
        assert not result.error
        assert ".json" in (result.message or "")

    async def test_export_to_custom_path(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState, tmp_path: Path
    ) -> None:
        out = tmp_path / "my_session.md"
        result = await registry.dispatch(f"/export markdown {out}", ctx, state)
        assert not result.error
        assert out.exists()

    async def test_export_invalid_range_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/export markdown --range bad-range", ctx, state)
        assert result.error


# ── /compare ─────────────────────────────────────────────────────────────────


class TestCompareCommand:
    async def test_compare_no_args_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/compare", ctx, state)
        assert result.error

    async def test_compare_one_alias_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        _add_alias(ctx, "a1")
        result = await registry.dispatch("/compare a1", ctx, state)
        assert result.error

    async def test_compare_unknown_aliases_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/compare ghost1 ghost2", ctx, state)
        assert result.error
        assert "Unknown" in (result.message or "")

    async def test_compare_sets_compare_request_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.model_registry.add(ModelAlias("m1", "openai", "gpt-4o", 128000))
        ctx.model_registry.add(ModelAlias("m2", "anthropic", "claude-sonnet-4-6", 200000))
        result = await registry.dispatch("/compare m1 m2", ctx, state)
        assert not result.error
        assert result.action == "compare_request"
        assert result.extra.get("aliases") == ["m1", "m2"]


# ── /schedule ─────────────────────────────────────────────────────────────────


class TestScheduleCommand:
    async def test_schedule_list_empty(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/schedule list", ctx, state)
        assert not result.error
        assert "No schedules" in (result.message or "")

    async def test_schedule_add(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch(
            '/schedule add morning "0 9 * * *" Check emails', ctx, state
        )
        assert not result.error
        assert ctx.schedule_manager.exists("morning")

    async def test_schedule_remove(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from anythink.schedule.models import ScheduledPrompt

        ctx.schedule_manager.add(ScheduledPrompt("to-del", "* * * * *", "prompt"))
        result = await registry.dispatch("/schedule remove to-del", ctx, state)
        assert not result.error
        assert not ctx.schedule_manager.exists("to-del")

    async def test_schedule_enable(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from anythink.schedule.models import ScheduledPrompt

        ctx.schedule_manager.add(ScheduledPrompt("s1", "* * * * *", "p", enabled=False))
        result = await registry.dispatch("/schedule enable s1", ctx, state)
        assert not result.error
        assert ctx.schedule_manager.get("s1").enabled  # type: ignore[union-attr]

    async def test_schedule_disable(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from anythink.schedule.models import ScheduledPrompt

        ctx.schedule_manager.add(ScheduledPrompt("s2", "* * * * *", "p"))
        result = await registry.dispatch("/schedule disable s2", ctx, state)
        assert not result.error
        assert not ctx.schedule_manager.get("s2").enabled  # type: ignore[union-attr]

    async def test_schedule_run_fires_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from anythink.schedule.models import ScheduledPrompt

        ctx.schedule_manager.add(ScheduledPrompt("auto", "0 8 * * *", "do it"))
        result = await registry.dispatch("/schedule run auto", ctx, state)
        assert not result.error
        assert result.action == "schedule_run"
        assert result.extra.get("schedule_name") == "auto"

    async def test_schedule_run_unknown_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/schedule run ghost", ctx, state)
        assert result.error

    async def test_schedule_bad_subcommand_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/schedule badcmd", ctx, state)
        assert result.error


# ── V3 commands registered ─────────────────────────────────────────────────────


class TestV3CommandsRegistered:
    def test_all_v3_commands_in_registry(self, registry: CommandRegistry) -> None:
        v3_commands = {
            "params",
            "cost",
            "template",
            "use",
            "doctor",
            "update",
            "config",
            "export",
            "compare",
            "schedule",
        }
        registered = set(registry.names())
        assert v3_commands.issubset(registered)
