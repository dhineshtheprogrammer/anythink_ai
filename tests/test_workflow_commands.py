"""Tests for workflow/commands.py — the /workflow slash-command namespace."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from anythink.app.chat import ChatState
from anythink.app.context import AppContext
from anythink.commands.handlers import register_commands
from anythink.commands.registry import CommandRegistry
from anythink.config.manager import Paths
from anythink.exceptions import WorkflowError
from anythink.workflow.commands import (
    _format_plan,
    _wf_help,
    register_workflow_commands,
)
from anythink.workflow.models import Stage, StageType, WorkflowPlan

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan(name: str = "test-plan", n_stages: int = 2) -> WorkflowPlan:
    stages = [
        Stage(
            id=f"stage_{i}",
            type=StageType.LLM_SPECIALIST,
            label=f"Step {i}",
            model_alias="gpt4o",
        )
        for i in range(1, n_stages + 1)
    ]
    return WorkflowPlan(
        name=name,
        trigger="summarize emails",
        stages=stages,
        models_used=["gpt4o"],
        mcp_servers_used=[],
    )


def _make_provider() -> MagicMock:
    p = MagicMock()
    p.name = "mock"
    return p


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ctx(xdg_dirs: Paths) -> AppContext:
    return AppContext.create(paths=xdg_dirs, console_file=StringIO())


@pytest.fixture()
def state(ctx: AppContext) -> ChatState:
    return ChatState(provider=_make_provider(), model_id="llama3", context_window=8192)


@pytest.fixture()
def registry(ctx: AppContext) -> CommandRegistry:
    r = CommandRegistry()
    register_commands(r)
    return r


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_workflow_command_registered(self, registry: CommandRegistry) -> None:
        assert "workflow" in registry.names()

    def test_register_workflow_commands_standalone(self) -> None:
        r = CommandRegistry()
        register_workflow_commands(r)
        assert "workflow" in r.names()


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


class TestHelp:
    async def test_no_args_shows_help(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow", ctx, state)
        assert result.message is not None
        assert "run" in result.message
        assert "list" in result.message

    async def test_help_subcommand(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow help", ctx, state)
        assert result.message is not None
        assert not result.error

    def test_wf_help_standalone(self) -> None:
        result = _wf_help()
        assert "manifest" in result.message
        assert "registry" in result.message

    async def test_unknown_subcommand_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow bogus", ctx, state)
        assert result.error
        assert "bogus" in result.message


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    async def test_run_quoted_task_returns_run_request(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch('/workflow run "summarize emails"', ctx, state)
        assert result.action == "workflow_run_request"
        assert result.extra["task"] == "summarize emails"
        assert result.extra["is_named"] is False

    async def test_run_single_quoted_task(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow run 'summarize emails'", ctx, state)
        assert result.action == "workflow_run_request"
        assert result.extra["task"] == "summarize emails"

    async def test_run_dry_run_quoted_returns_dry_run_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch('/workflow run "summarize emails" --dry-run', ctx, state)
        assert result.action == "workflow_dry_run_request"
        assert result.extra["task"] == "summarize emails"

    async def test_run_named_workflow_found(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_storage.save("my-flow", _make_plan("my-flow"))
        result = await registry.dispatch("/workflow run my-flow", ctx, state)
        assert result.action == "workflow_run_request"
        assert result.extra["name"] == "my-flow"
        assert result.extra["is_named"] is True

    async def test_run_named_workflow_dry_run(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_storage.save("my-flow", _make_plan("my-flow"))
        result = await registry.dispatch("/workflow run my-flow --dry-run", ctx, state)
        assert result.action == "workflow_dry_run_request"
        assert result.extra["is_named"] is True

    async def test_run_unquoted_unknown_name_treated_as_task(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow run summarize-emails", ctx, state)
        assert result.action == "workflow_run_request"
        assert result.extra["task"] == "summarize-emails"
        assert result.extra["is_named"] is False

    async def test_run_no_args_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow run", ctx, state)
        assert result.error

    async def test_run_empty_quoted_task_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch('/workflow run ""', ctx, state)
        assert result.error


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------


class TestNew:
    async def test_new_returns_wizard_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow new", ctx, state)
        assert result.action == "workflow_new_wizard"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestList:
    async def test_list_empty_storage(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow list", ctx, state)
        assert not result.error
        assert "No saved workflows" in result.message

    async def test_list_shows_saved_names(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_storage.save("alpha", _make_plan("alpha"))
        ctx.workflow_storage.save("beta", _make_plan("beta"))
        result = await registry.dispatch("/workflow list", ctx, state)
        assert "alpha" in result.message
        assert "beta" in result.message


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


class TestShow:
    async def test_show_no_name_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow show", ctx, state)
        assert result.error

    async def test_show_nonexistent_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow show nonexistent", ctx, state)
        assert result.error

    async def test_show_existing_plan(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_storage.save("my-plan", _make_plan("my-plan"))
        result = await registry.dispatch("/workflow show my-plan", ctx, state)
        assert not result.error
        assert "my-plan" in result.message
        assert "LLM_SPECIALIST" in result.message

    def test_format_plan_contains_key_fields(self) -> None:
        plan = _make_plan("demo", n_stages=1)
        text = _format_plan(plan)
        assert "demo" in text
        assert "summarize emails" in text
        assert "LLM_SPECIALIST" in text


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


class TestEdit:
    async def test_edit_no_name_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow edit", ctx, state)
        assert result.error

    async def test_edit_nonexistent_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow edit ghost", ctx, state)
        assert result.error

    async def test_edit_existing_returns_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_storage.save("my-plan", _make_plan("my-plan"))
        result = await registry.dispatch("/workflow edit my-plan", ctx, state)
        assert result.action == "workflow_edit_request"
        assert result.extra["name"] == "my-plan"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    async def test_delete_no_name_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow delete", ctx, state)
        assert result.error

    async def test_delete_nonexistent_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow delete ghost", ctx, state)
        assert result.error

    async def test_delete_existing_succeeds(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_storage.save("to-delete", _make_plan("to-delete"))
        result = await registry.dispatch("/workflow delete to-delete", ctx, state)
        assert not result.error
        assert "deleted" in result.message.lower()
        assert "to-delete" not in ctx.workflow_storage.list_names()


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------


class TestRename:
    async def test_rename_missing_args_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow rename only-one", ctx, state)
        assert result.error

    async def test_rename_nonexistent_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow rename ghost new-name", ctx, state)
        assert result.error

    async def test_rename_existing_succeeds(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_storage.save("old-name", _make_plan("old-name"))
        result = await registry.dispatch("/workflow rename old-name new-name", ctx, state)
        assert not result.error
        assert "new-name" in ctx.workflow_storage.list_names()
        assert "old-name" not in ctx.workflow_storage.list_names()


# ---------------------------------------------------------------------------
# stop / pause / resume / status
# ---------------------------------------------------------------------------


class TestControlActions:
    async def test_stop_returns_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow stop", ctx, state)
        assert result.action == "workflow_stop"

    async def test_pause_returns_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow pause", ctx, state)
        assert result.action == "workflow_pause"

    async def test_resume_returns_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow resume", ctx, state)
        assert result.action == "workflow_resume"

    async def test_status_returns_action(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow status", ctx, state)
        assert result.action == "workflow_status_request"


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


class TestLogs:
    async def test_logs_no_entries(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow logs", ctx, state)
        assert not result.error
        assert "No workflow logs" in result.message

    async def test_logs_last_no_entries(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow logs last", ctx, state)
        assert not result.error
        assert "No workflow logs" in result.message

    async def test_logs_last_with_log_file(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState, xdg_dirs: Paths
    ) -> None:
        log_dir = xdg_dirs.data_dir / "workflow_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fake_log = log_dir / "2026-01-01_120000_test.log"
        fake_log.write_text("log content")

        result = await registry.dispatch("/workflow logs last", ctx, state)
        assert result.action == "open_file_in_editor"
        assert str(fake_log) in result.extra["path"]

    async def test_logs_list_shows_files(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState, xdg_dirs: Paths
    ) -> None:
        log_dir = xdg_dirs.data_dir / "workflow_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "2026-01-01_120000_alpha.log").write_text("x")
        (log_dir / "2026-01-02_130000_beta.log").write_text("x")

        result = await registry.dispatch("/workflow logs", ctx, state)
        assert "alpha" in result.message or "beta" in result.message

    async def test_logs_show_index(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState, xdg_dirs: Paths
    ) -> None:
        log_dir = xdg_dirs.data_dir / "workflow_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fake_log = log_dir / "2026-01-01_120000_test.log"
        fake_log.write_text("content")

        result = await registry.dispatch("/workflow logs show 1", ctx, state)
        assert result.action == "open_file_in_editor"

    async def test_logs_show_out_of_range(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState, xdg_dirs: Paths
    ) -> None:
        log_dir = xdg_dirs.data_dir / "workflow_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "2026-01-01_120000_test.log").write_text("x")

        result = await registry.dispatch("/workflow logs show 99", ctx, state)
        assert result.error

    async def test_logs_show_no_arg_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow logs show", ctx, state)
        assert result.error


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------


class TestManifest:
    async def test_manifest_path(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState, xdg_dirs: Paths
    ) -> None:
        result = await registry.dispatch("/workflow manifest path", ctx, state)
        assert not result.error
        assert "workflow_manifest.txt" in result.message

    async def test_manifest_show(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow manifest show", ctx, state)
        assert not result.error
        # manifest was written on ctx creation; should have content
        assert result.message

    async def test_manifest_refresh(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow manifest refresh", ctx, state)
        assert not result.error
        assert "refreshed" in result.message.lower()

    async def test_manifest_no_subcommand_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow manifest", ctx, state)
        assert result.error

    async def test_manifest_show_empty_returns_hint(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState, xdg_dirs: Paths
    ) -> None:
        # Overwrite manifest with empty file
        (xdg_dirs.config_dir / "workflow_manifest.txt").write_text("")
        result = await registry.dispatch("/workflow manifest show", ctx, state)
        assert not result.error
        assert "refresh" in result.message.lower()


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


class TestRegistryCommands:
    async def test_registry_list_empty(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow registry list", ctx, state)
        assert not result.error
        assert "empty" in result.message.lower() or "registry" in result.message.lower()

    async def test_registry_add_tag(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch(
            "/workflow registry add-tag gpt4o summarization", ctx, state
        )
        assert not result.error
        assert "summarization" in result.message

    async def test_registry_add_tag_missing_args(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow registry add-tag gpt4o", ctx, state)
        assert result.error

    async def test_registry_list_after_add(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_registry.add_tag("gpt4o", "reasoning")
        result = await registry.dispatch("/workflow registry list", ctx, state)
        assert "gpt4o" in result.message
        assert "reasoning" in result.message

    async def test_registry_tags_for_alias(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_registry.add_tag("llama3", "planning")
        result = await registry.dispatch("/workflow registry tags llama3", ctx, state)
        assert "planning" in result.message

    async def test_registry_tags_no_alias_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow registry tags", ctx, state)
        assert result.error

    async def test_registry_remove_tag(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_registry.add_tag("gpt4o", "coding")
        result = await registry.dispatch("/workflow registry remove-tag gpt4o coding", ctx, state)
        assert not result.error
        assert "coding" in result.message

    async def test_registry_remove_tag_missing_args(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow registry remove-tag gpt4o", ctx, state)
        assert result.error

    async def test_registry_fallback_set(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow registry fallback gpt4o gpt35", ctx, state)
        assert not result.error
        assert "gpt35" in result.message

    async def test_registry_fallback_missing_args(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow registry fallback gpt4o", ctx, state)
        assert result.error

    async def test_registry_fallback_chain_no_chain(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow registry fallback-chain gpt4o", ctx, state)
        assert not result.error
        assert "no fallback" in result.message.lower()

    async def test_registry_fallback_chain_with_chain(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_registry.set_fallback("gpt4o", "gpt35")
        ctx.workflow_registry.set_fallback("gpt35", "llama3")
        result = await registry.dispatch("/workflow registry fallback-chain gpt4o", ctx, state)
        assert "gpt4o" in result.message
        assert "gpt35" in result.message

    async def test_registry_fallback_chain_alias(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.workflow_registry.set_fallback("gpt4o", "gpt35")
        result = await registry.dispatch("/workflow registry chain gpt4o", ctx, state)
        assert not result.error

    async def test_registry_fallback_chain_no_alias_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow registry fallback-chain", ctx, state)
        assert result.error

    async def test_registry_unknown_subcommand_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/workflow registry bogus", ctx, state)
        assert result.error
