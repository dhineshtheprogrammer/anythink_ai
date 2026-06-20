"""Tests for mcp/models.py."""

from __future__ import annotations

from anythink.mcp.models import MCPCallResult, MCPConnectConfig, MCPServerInfo, MCPTool


class TestMCPTool:
    def test_fields(self) -> None:
        t = MCPTool("my_tool", "Does something.", {"x": "string"}, "my_server")
        assert t.name == "my_tool"
        assert t.server_name == "my_server"
        assert "x" in t.input_schema


class TestMCPCallResult:
    def test_defaults(self) -> None:
        r = MCPCallResult("tool", "server", "content")
        assert not r.is_error
        assert r.duration_s == 0.0

    def test_error_flag(self) -> None:
        r = MCPCallResult("tool", "server", "oops", is_error=True)
        assert r.is_error


class TestMCPServerInfo:
    def test_defaults(self) -> None:
        s = MCPServerInfo(name="fs", kind="builtin", transport="builtin")
        assert s.connected
        assert s.tool_count == 0


class TestMCPConnectConfig:
    def test_stdio_config(self) -> None:
        c = MCPConnectConfig(name="ext", transport="stdio", command="python server.py")
        assert c.transport == "stdio"
        assert c.command == "python server.py"
        assert c.url == ""

    def test_sse_config(self) -> None:
        c = MCPConnectConfig(name="remote", transport="sse", url="http://localhost:8765")
        assert c.transport == "sse"
        assert c.url == "http://localhost:8765"
