"""Tests for the /mcp windows command sub-namespace."""

from __future__ import annotations

import os
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.app.chat import ChatState
from anythink.app.context import AppContext
from anythink.commands.handlers import _mcp_windows, register_commands
from anythink.commands.registry import CommandRegistry
from anythink.config.manager import Paths
from anythink.config.schema import AppConfig
from anythink.mcp.manager import MCPManager
from anythink.mcp.models import MCPCallResult


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
    return ChatState(provider=provider, model_id="gpt-4", context_window=8192)


# ── Status ────────────────────────────────────────────────────────────────────


class TestMCPWindowsStatus:
    async def test_status_when_disabled(self, ctx: AppContext, state: ChatState) -> None:
        result = await _mcp_windows(ctx, "", state)
        assert not result.error
        assert "disabled" in (result.message or "").lower() or "windows" in (result.message or "").lower()

    async def test_status_shows_enabled_info(self, ctx: AppContext, state: ChatState) -> None:
        from dataclasses import replace
        ctx.config = replace(ctx.config, windows_enabled=True)
        result = await _mcp_windows(ctx, "status", state)
        assert not result.error


# ── Mode ──────────────────────────────────────────────────────────────────────


class TestMCPWindowsMode:
    async def test_mode_gui_updates_config(self, ctx: AppContext, state: ChatState) -> None:
        assert not ctx.config.windows_gui_mode
        result = await _mcp_windows(ctx, "mode gui", state)
        assert not result.error
        assert ctx.config.windows_gui_mode is True

    async def test_mode_headless_updates_config(self, ctx: AppContext, state: ChatState) -> None:
        from dataclasses import replace
        ctx.config = replace(ctx.config, windows_gui_mode=True)
        result = await _mcp_windows(ctx, "mode headless", state)
        assert not result.error
        assert ctx.config.windows_gui_mode is False

    async def test_mode_invalid_returns_error(self, ctx: AppContext, state: ChatState) -> None:
        result = await _mcp_windows(ctx, "mode turbo", state)
        assert result.error


# ── Paths ─────────────────────────────────────────────────────────────────────


class TestMCPWindowsPaths:
    async def test_paths_list_without_server(self, ctx: AppContext, state: ChatState) -> None:
        result = await _mcp_windows(ctx, "paths list", state)
        # Without a registered windows-filesystem server, should return a message
        assert not result.error

    async def test_paths_allow_without_server_returns_message(
        self, ctx: AppContext, state: ChatState
    ) -> None:
        result = await _mcp_windows(ctx, "paths allow C:\\MyProject\\", state)
        assert not result.error

    async def test_paths_invalid_subcommand(self, ctx: AppContext, state: ChatState) -> None:
        result = await _mcp_windows(ctx, "paths", state)
        # "paths" with no subcommand defaults to "list" — should not error
        assert not result.error or "usage" in (result.message or "").lower()


# ── Apps ──────────────────────────────────────────────────────────────────────


class TestMCPWindowsApps:
    async def test_apps_invokes_list_installed(self, ctx: AppContext, state: ChatState) -> None:
        mock_result = MCPCallResult(
            tool_name="list_installed_apps",
            server_name="windows-apps",
            content="Installed Applications (0 found)",
        )
        ctx.mcp_manager.call_tool = AsyncMock(return_value=mock_result)  # type: ignore[method-assign]
        result = await _mcp_windows(ctx, "apps", state)
        ctx.mcp_manager.call_tool.assert_called_once_with("list_installed_apps", {})
        assert "Installed" in (result.message or "")

    async def test_apps_block_updates_config(self, ctx: AppContext, state: ChatState) -> None:
        assert "mspaint.exe" not in ctx.config.windows_blocked_apps
        result = await _mcp_windows(ctx, "apps block mspaint.exe", state)
        assert not result.error
        assert "mspaint.exe" in ctx.config.windows_blocked_apps

    async def test_apps_unblock_removes_from_config(self, ctx: AppContext, state: ChatState) -> None:
        from dataclasses import replace
        ctx.config = replace(
            ctx.config,
            windows_blocked_apps=ctx.config.windows_blocked_apps + ("mspaint.exe",),
        )
        result = await _mcp_windows(ctx, "apps unblock mspaint.exe", state)
        assert not result.error
        assert "mspaint.exe" not in ctx.config.windows_blocked_apps


# ── Audit ─────────────────────────────────────────────────────────────────────


class TestMCPWindowsAudit:
    async def test_audit_without_server_returns_message(
        self, ctx: AppContext, state: ChatState
    ) -> None:
        result = await _mcp_windows(ctx, "audit", state)
        assert not result.error
        assert "not active" in (result.message or "").lower() or "no audit" in (result.message or "").lower()

    async def test_audit_clear_returns_action_not_immediate(
        self, ctx: AppContext, state: ChatState
    ) -> None:
        """Key spec compliance: audit clear must return action signal, not immediately clear."""
        result = await _mcp_windows(ctx, "audit clear", state)
        assert not result.error
        assert result.action == "windows_audit_clear_confirm"
        assert "confirm" in (result.message or "").lower() or "yes" in (result.message or "").lower()


# ── Quick Actions ─────────────────────────────────────────────────────────────


class TestMCPWindowsQuickActions:
    async def test_screenshot_returns_mcp_call_request_action(
        self, ctx: AppContext, state: ChatState
    ) -> None:
        result = await _mcp_windows(ctx, "screenshot", state)
        assert not result.error
        assert result.action == "mcp_call_request"
        assert result.extra.get("tool") == "take_screenshot"

    async def test_clip_read_invokes_read_clipboard(
        self, ctx: AppContext, state: ChatState
    ) -> None:
        mock_result = MCPCallResult(
            tool_name="read_clipboard",
            server_name="windows-clipboard",
            content="clipboard content",
        )
        ctx.mcp_manager.call_tool = AsyncMock(return_value=mock_result)  # type: ignore[method-assign]
        result = await _mcp_windows(ctx, "clip read", state)
        ctx.mcp_manager.call_tool.assert_called_once_with("read_clipboard", {})
        assert "clipboard content" in (result.message or "")

    async def test_clip_write_invokes_write_clipboard(
        self, ctx: AppContext, state: ChatState
    ) -> None:
        mock_result = MCPCallResult(
            tool_name="write_clipboard",
            server_name="windows-clipboard",
            content="5 characters written.",
        )
        ctx.mcp_manager.call_tool = AsyncMock(return_value=mock_result)  # type: ignore[method-assign]
        result = await _mcp_windows(ctx, "clip write hello", state)
        ctx.mcp_manager.call_tool.assert_called_once_with("write_clipboard", {"text": "hello"})

    async def test_clip_write_without_text_returns_error(
        self, ctx: AppContext, state: ChatState
    ) -> None:
        result = await _mcp_windows(ctx, "clip write", state)
        assert result.error

    async def test_notify_invokes_send_notification(
        self, ctx: AppContext, state: ChatState
    ) -> None:
        mock_result = MCPCallResult(
            tool_name="send_notification",
            server_name="windows-notification",
            content="Notification sent.",
        )
        ctx.mcp_manager.call_tool = AsyncMock(return_value=mock_result)  # type: ignore[method-assign]
        result = await _mcp_windows(ctx, "notify Test message", state)
        call_args = ctx.mcp_manager.call_tool.call_args
        assert call_args[0][0] == "send_notification"
        assert call_args[0][1]["message"] == "Test message"

    async def test_notify_without_message_returns_error(
        self, ctx: AppContext, state: ChatState
    ) -> None:
        result = await _mcp_windows(ctx, "notify", state)
        assert result.error

    async def test_unknown_subcommand_returns_error(
        self, ctx: AppContext, state: ChatState
    ) -> None:
        result = await _mcp_windows(ctx, "frobulate", state)
        assert result.error
