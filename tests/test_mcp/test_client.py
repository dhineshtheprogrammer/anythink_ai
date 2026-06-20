"""Tests for mcp/client.py."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.mcp.client import MCPClient


class TestMCPClientNoSDK:
    async def test_connect_raises_without_mcp_sdk(self) -> None:
        """connect() raises MCPError when the mcp SDK is not installed."""
        from anythink.exceptions import MCPError

        client = MCPClient("test", "stdio", command="python server.py")

        with patch.dict(sys.modules, {"mcp": None}):
            with pytest.raises(MCPError, match="mcp SDK"):
                await client.connect()

    def test_initial_state(self) -> None:
        client = MCPClient("srv", "stdio", command="cmd")
        assert client.name == "srv"
        assert client.transport == "stdio"
        assert not client.is_connected
        assert client.tool_count == 0
        assert client.cached_tools == []

    async def test_call_tool_when_not_connected(self) -> None:
        client = MCPClient("srv", "stdio", command="cmd")
        result = await client.call_tool("my_tool", {})
        assert result.is_error
        assert "Not connected" in result.content

    async def test_disconnect_when_not_connected(self) -> None:
        """disconnect() when not connected should not raise."""
        client = MCPClient("srv", "stdio", command="cmd")
        await client.disconnect()  # must not raise
        assert not client.is_connected


class TestMCPClientWithMockedSDK:
    async def test_connect_stdio_success(self) -> None:
        client = MCPClient("test", "stdio", command="python server.py")

        mock_tool = MagicMock()
        mock_tool.name = "greet"
        mock_tool.description = "Say hello."
        mock_tool.inputSchema = {"name": "string"}

        mock_response = MagicMock()
        mock_response.tools = [mock_tool]

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_transport = (AsyncMock(), AsyncMock())
        mock_stdio_ctx = AsyncMock()
        mock_stdio_ctx.__aenter__ = AsyncMock(return_value=mock_transport)
        mock_stdio_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client_session_cls = MagicMock(return_value=mock_session)
        mock_stdio_client = MagicMock(return_value=mock_stdio_ctx)

        mock_mcp = MagicMock()
        mock_mcp.ClientSession = mock_client_session_cls
        mock_mcp.StdioServerParameters = MagicMock()

        mock_stdio_module = MagicMock()
        mock_stdio_module.stdio_client = mock_stdio_client

        with patch.dict(
            sys.modules,
            {"mcp": mock_mcp, "mcp.client.stdio": mock_stdio_module},
        ):
            await client.connect()

        assert client.is_connected
        assert client.tool_count == 1
        assert client.cached_tools[0].name == "greet"

    async def test_call_tool_success(self) -> None:
        client = MCPClient("test", "stdio", command="python server.py")

        mock_content_item = MagicMock()
        mock_content_item.text = "hello, world"

        mock_call_result = MagicMock()
        mock_call_result.content = [mock_content_item]
        mock_call_result.isError = False

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_call_result)
        client._session = mock_session

        result = await client.call_tool("greet", {"name": "Alice"})
        assert not result.is_error
        assert "hello, world" in result.content
        assert result.tool_name == "greet"

    async def test_call_tool_error_response(self) -> None:
        client = MCPClient("test", "stdio", command="python server.py")

        mock_call_result = MagicMock()
        mock_call_result.content = []
        mock_call_result.isError = True

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_call_result)
        client._session = mock_session

        result = await client.call_tool("bad_tool", {})
        assert result.is_error

    async def test_call_tool_exception(self) -> None:
        client = MCPClient("test", "stdio", command="python server.py")
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(side_effect=Exception("network error"))
        client._session = mock_session

        result = await client.call_tool("any_tool", {})
        assert result.is_error
        assert "network error" in result.content

    async def test_unknown_transport_raises(self) -> None:
        from anythink.exceptions import MCPError

        client = MCPClient("test", "unknown_transport")

        mock_mcp = MagicMock()
        mock_mcp.ClientSession = MagicMock()

        with patch.dict(sys.modules, {"mcp": mock_mcp}):
            with pytest.raises(MCPError, match="Unknown transport"):
                await client.connect()
