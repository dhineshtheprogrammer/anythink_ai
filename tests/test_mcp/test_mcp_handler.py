"""Tests for the /mcp slash command handler."""

from __future__ import annotations

from io import StringIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from anythink.app.chat import ChatState
from anythink.app.context import AppContext
from anythink.commands.handlers import register_commands
from anythink.commands.registry import CommandRegistry
from anythink.config.manager import Paths
from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.manager import MCPManager
from anythink.mcp.models import MCPCallResult, MCPTool


class _HelloServer(BuiltinMCPServer):
    name = "hello"
    description = "Test server."

    def list_tools(self) -> list[MCPTool]:
        return [MCPTool("greet", "Say hi.", {"name": "string"}, self.name)]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        return MCPCallResult(tool_name=name, server_name=self.name, content="Hi!")


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


class TestMCPStatusCommand:
    async def test_status_no_servers(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager()
        result = await registry.dispatch("/mcp status", ctx, state)
        assert not result.error
        assert "0 server" in result.message or "status" in (result.message or "").lower()

    async def test_status_with_builtin(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager([_HelloServer()])
        result = await registry.dispatch("/mcp status", ctx, state)
        assert not result.error
        assert "1 server" in (result.message or "")

    async def test_status_no_args(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager([_HelloServer()])
        result = await registry.dispatch("/mcp", ctx, state)
        assert not result.error


class TestMCPListCommand:
    async def test_list_empty(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager()
        result = await registry.dispatch("/mcp list", ctx, state)
        assert not result.error
        assert "No MCP servers" in (result.message or "")

    async def test_list_with_server(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager([_HelloServer()])
        result = await registry.dispatch("/mcp list", ctx, state)
        assert not result.error
        assert "hello" in (result.message or "")
        assert "builtin" in (result.message or "")


class TestMCPToolsCommand:
    async def test_tools_empty(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager()
        result = await registry.dispatch("/mcp tools", ctx, state)
        assert not result.error
        assert "No MCP tools" in (result.message or "")

    async def test_tools_with_server(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager([_HelloServer()])
        result = await registry.dispatch("/mcp tools", ctx, state)
        assert not result.error
        assert "greet" in (result.message or "")
        assert "hello" in (result.message or "")


class TestMCPCallCommand:
    async def test_call_returns_request_action(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager([_HelloServer()])
        result = await registry.dispatch("/mcp call greet name=Alice", ctx, state)
        assert not result.error
        assert result.action == "mcp_call_request"
        assert result.extra.get("tool") == "greet"
        assert result.extra.get("name") == "Alice"

    async def test_call_no_tool_name(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager()
        result = await registry.dispatch("/mcp call", ctx, state)
        assert result.error

    async def test_call_no_kwargs(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager([_HelloServer()])
        result = await registry.dispatch("/mcp call greet", ctx, state)
        assert not result.error
        assert result.action == "mcp_call_request"
        assert result.extra.get("tool") == "greet"


class TestMCPConnectCommand:
    async def test_connect_missing_args(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager()
        result = await registry.dispatch("/mcp connect myserver", ctx, state)
        assert result.error

    async def test_connect_mcp_unavailable(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        import sys

        from unittest.mock import patch

        ctx.mcp_manager = MCPManager()
        with patch.dict(sys.modules, {"mcp": None}):
            result = await registry.dispatch("/mcp connect ext stdio python server.py", ctx, state)
        assert result.error
        assert "mcp" in (result.message or "").lower()


class TestMCPDisconnectCommand:
    async def test_disconnect_unknown(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager()
        result = await registry.dispatch("/mcp disconnect nobody", ctx, state)
        assert result.error

    async def test_disconnect_no_arg(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager()
        result = await registry.dispatch("/mcp disconnect", ctx, state)
        assert result.error


class TestMCPServerCommand:
    async def test_server_status(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager()
        result = await registry.dispatch("/mcp server status", ctx, state)
        assert not result.error
        assert "not running" in (result.message or "").lower()

    async def test_server_stop(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager()
        result = await registry.dispatch("/mcp server stop", ctx, state)
        assert not result.error

    async def test_server_start_no_sdk(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        import sys

        from unittest.mock import patch

        ctx.mcp_manager = MCPManager()
        with patch.dict(sys.modules, {"mcp": None, "mcp.server": None, "mcp.server.fastmcp": None}):
            result = await registry.dispatch("/mcp server start", ctx, state)
        assert result.error

    async def test_server_invalid_subcommand(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager()
        result = await registry.dispatch("/mcp server badcmd", ctx, state)
        assert result.error


class TestMCPUnknownSubcommand:
    async def test_unknown_returns_error(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.mcp_manager = MCPManager()
        result = await registry.dispatch("/mcp badsubcommand", ctx, state)
        assert result.error
