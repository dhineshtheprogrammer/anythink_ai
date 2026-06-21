"""Tests for mcp/server.py."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from anythink.mcp.manager import MCPManager
from anythink.mcp.server import AnythinkMCPServer


class TestAnythinkMCPServerProperties:
    def test_initial_state(self) -> None:
        mgr = MCPManager()
        srv = AnythinkMCPServer(mgr)
        assert not srv.is_running
        assert srv.address == ""

    async def test_stop_when_not_running(self) -> None:
        mgr = MCPManager()
        srv = AnythinkMCPServer(mgr)
        await srv.stop()  # must not raise
        assert not srv.is_running

    async def test_start_raises_without_mcp_sdk(self) -> None:
        from anythink.exceptions import MCPError

        mgr = MCPManager()
        srv = AnythinkMCPServer(mgr)

        with patch.dict(sys.modules, {"mcp": None, "mcp.server": None, "mcp.server.fastmcp": None}):
            with pytest.raises(MCPError, match="mcp SDK"):
                await srv.start()

    async def test_start_with_mocked_fastmcp(self) -> None:
        """start() returns an address and sets is_running when SDK is available."""
        from anythink.mcp.builtin.filesystem import FilesystemServer

        mgr = MCPManager([FilesystemServer()])
        srv = AnythinkMCPServer(mgr)

        mock_app = MagicMock()
        mock_fastmcp_cls = MagicMock(return_value=mock_app)

        mock_server_mod = MagicMock()
        mock_server_mod.FastMCP = mock_fastmcp_cls
        mock_fastmcp_mod = MagicMock()
        mock_fastmcp_mod.FastMCP = mock_fastmcp_cls

        with patch.dict(
            sys.modules,
            {
                "mcp": MagicMock(),
                "mcp.server": mock_server_mod,
                "mcp.server.fastmcp": mock_fastmcp_mod,
            },
        ):
            address = await srv.start(host="127.0.0.1", port=9876)

        assert srv.is_running
        assert "127.0.0.1" in address
        assert "9876" in address

    async def test_stop_after_start(self) -> None:
        mgr = MCPManager()
        srv = AnythinkMCPServer(mgr)
        # Manually set running state (bypassing SDK)
        srv._running = True
        srv._address = "http://localhost:8765/sse"

        await srv.stop()
        assert not srv.is_running
        assert srv.address == ""
