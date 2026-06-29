"""Tests for mcp/manager.py."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.manager import MCPManager
from anythink.mcp.models import MCPCallResult, MCPConnectConfig, MCPTool


class _EchoServer(BuiltinMCPServer):
    """Simple built-in server that echoes arguments back."""

    name = "echo"
    description = "Echo test server."

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool("echo", "Echo arguments.", {"msg": "string"}, self.name),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        if name == "echo":
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content=str(arguments.get("msg", "")),
            )
        return MCPCallResult(tool_name=name, server_name=self.name, content="?", is_error=True)


class _BrokenServer(BuiltinMCPServer):
    name = "broken"
    description = "Always errors."

    def list_tools(self) -> list[MCPTool]:
        return [MCPTool("bad", "Fails.", {}, self.name)]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        return MCPCallResult(tool_name=name, server_name=self.name, content="err", is_error=True)


class TestMCPManagerBuiltins:
    def test_register_builtin_indexes_tools(self) -> None:
        mgr = MCPManager([_EchoServer()])
        assert "echo" in mgr._tool_index
        assert mgr._tool_index["echo"] == "echo"

    def test_list_servers_includes_builtin(self) -> None:
        mgr = MCPManager([_EchoServer()])
        servers = mgr.list_servers()
        assert any(s.name == "echo" and s.kind == "builtin" for s in servers)

    def test_list_tools_returns_all(self) -> None:
        mgr = MCPManager([_EchoServer(), _BrokenServer()])
        names = {t.name for t in mgr.list_tools()}
        assert "echo" in names
        assert "bad" in names

    def test_get_tool_found(self) -> None:
        mgr = MCPManager([_EchoServer()])
        tool = mgr.get_tool("echo")
        assert tool is not None
        assert tool.server_name == "echo"

    def test_get_tool_not_found(self) -> None:
        mgr = MCPManager()
        assert mgr.get_tool("nope") is None

    async def test_call_tool_routes_correctly(self) -> None:
        mgr = MCPManager([_EchoServer()])
        result = await mgr.call_tool("echo", {"msg": "hello"})
        assert not result.is_error
        assert result.content == "hello"

    async def test_call_unknown_tool(self) -> None:
        mgr = MCPManager([_EchoServer()])
        result = await mgr.call_tool("nonexistent", {})
        assert result.is_error
        assert "Unknown tool" in result.content

    async def test_call_error_tool(self) -> None:
        mgr = MCPManager([_BrokenServer()])
        result = await mgr.call_tool("bad", {})
        assert result.is_error

    def test_empty_manager(self) -> None:
        mgr = MCPManager()
        assert mgr.list_servers() == []
        assert mgr.list_tools() == []


class TestMCPManagerExternal:
    async def test_connect_external_indexes_tools(self) -> None:
        mgr = MCPManager()

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.is_connected = True
        mock_client.tool_count = 2
        mock_client.transport = "stdio"
        mock_client._command = "python server.py"
        mock_client._url = ""
        mock_tool = MCPTool("ext_tool", "External tool.", {}, "ext")
        mock_client.cached_tools = [mock_tool]

        import anythink.mcp.client as client_mod

        orig_cls = client_mod.MCPClient
        try:
            client_mod.MCPClient = MagicMock(return_value=mock_client)  # type: ignore[attr-defined]
            config = MCPConnectConfig(name="ext", transport="stdio", command="python server.py")
            await mgr.connect(config)
        finally:
            client_mod.MCPClient = orig_cls  # type: ignore[attr-defined]

        assert "ext" in mgr._externals
        assert "ext_tool" in mgr._tool_index

    async def test_disconnect_removes_server_and_tools(self) -> None:
        mgr = MCPManager()

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.is_connected = True
        mock_client.tool_count = 1
        mock_client.transport = "stdio"
        mock_client._command = "python s.py"
        mock_client._url = ""
        mock_client.cached_tools = [MCPTool("t", "desc", {}, "ext")]

        import anythink.mcp.client as client_mod

        orig_cls = client_mod.MCPClient
        try:
            client_mod.MCPClient = MagicMock(return_value=mock_client)  # type: ignore[attr-defined]
            config = MCPConnectConfig(name="ext", transport="stdio", command="python s.py")
            await mgr.connect(config)
        finally:
            client_mod.MCPClient = orig_cls  # type: ignore[attr-defined]

        await mgr.disconnect("ext")
        assert "ext" not in mgr._externals
        assert "t" not in mgr._tool_index
        mock_client.disconnect.assert_called_once()

    async def test_disconnect_unknown_raises(self) -> None:
        from anythink.exceptions import MCPError

        mgr = MCPManager()
        with pytest.raises(MCPError):
            await mgr.disconnect("nobody")

    def test_list_servers_includes_external(self) -> None:
        mgr = MCPManager()
        mock_client = MagicMock()
        mock_client.transport = "sse"
        mock_client.is_connected = True
        mock_client.tool_count = 3
        mock_client._command = ""
        mock_client._url = "http://localhost/sse"
        mock_client.cached_tools = []
        mgr._externals["remote"] = mock_client

        servers = mgr.list_servers()
        ext = next(s for s in servers if s.name == "remote")
        assert ext.kind == "external"
        assert ext.transport == "sse"

    def test_list_tools_includes_external_client_tools(self) -> None:
        mgr = MCPManager()
        mock_client = MagicMock()
        mock_tool = MCPTool("ext_t", "desc", {}, "ext")
        mock_client.cached_tools = [mock_tool]
        mgr._externals["ext"] = mock_client
        tools = mgr.list_tools()
        assert any(t.name == "ext_t" for t in tools)

    async def test_call_tool_dispatches_to_external(self) -> None:
        mgr = MCPManager()
        mock_client = MagicMock()
        mock_client.call_tool = AsyncMock(
            return_value=MCPCallResult(tool_name="ext_t", server_name="ext", content="done")
        )
        mock_client.cached_tools = [MCPTool("ext_t", "desc", {}, "ext")]
        mgr._externals["ext"] = mock_client
        mgr._tool_index["ext_t"] = "ext"
        result = await mgr.call_tool("ext_t", {})
        assert not result.is_error
        assert result.content == "done"

    async def test_call_tool_stale_server_returns_error(self) -> None:
        mgr = MCPManager()
        mgr._tool_index["orphan_t"] = "ghost_server"
        result = await mgr.call_tool("orphan_t", {})
        assert result.is_error
        assert "no longer connected" in result.content

    async def test_reconnect_disconnects_existing_first(self) -> None:
        mgr = MCPManager()
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.is_connected = True
        mock_client.tool_count = 1
        mock_client.transport = "stdio"
        mock_client._command = "python s.py"
        mock_client._url = ""
        mock_client.cached_tools = []

        import anythink.mcp.client as client_mod

        orig_cls = client_mod.MCPClient
        try:
            client_mod.MCPClient = MagicMock(return_value=mock_client)  # type: ignore[attr-defined]
            config = MCPConnectConfig(name="ext2", transport="stdio", command="python s.py")
            await mgr.connect(config)
            # Second connect with same name should disconnect first
            await mgr.connect(config)
        finally:
            client_mod.MCPClient = orig_cls  # type: ignore[attr-defined]

        assert mock_client.disconnect.call_count >= 1
