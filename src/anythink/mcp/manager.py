"""MCPManager: orchestrates built-in and external MCP servers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from anythink.exceptions import MCPError
from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPConnectConfig, MCPServerInfo, MCPTool

if TYPE_CHECKING:
    from anythink.mcp.client import MCPClient


class MCPManager:
    """Central registry and dispatcher for all MCP servers.

    Built-in servers are registered at startup via ``register_builtin()``.
    External servers are connected on demand via ``connect()``.
    All tool calls are routed through ``call_tool()``.
    """

    def __init__(
        self,
        builtin_servers: list[BuiltinMCPServer] | None = None,
    ) -> None:
        self._builtins: dict[str, BuiltinMCPServer] = {}
        self._externals: dict[str, MCPClient] = {}  # name -> MCPClient
        # tool_name -> server_name (for routing)
        self._tool_index: dict[str, str] = {}

        for server in builtin_servers or []:
            self.register_builtin(server)

    # ── registration ──────────────────────────────────────────────────────────

    def register_builtin(self, server: BuiltinMCPServer) -> None:
        """Register a built-in server and index all its tools."""
        self._builtins[server.name] = server
        for tool in server.list_tools():
            self._tool_index[tool.name] = server.name

    # ── external connections ───────────────────────────────────────────────────

    async def connect(self, config: MCPConnectConfig) -> None:
        """Connect to an external MCP server and index its tools."""
        from anythink.mcp.client import MCPClient

        if config.name in self._externals:
            await self.disconnect(config.name)

        client = MCPClient(
            config.name,
            config.transport,
            command=config.command,
            url=config.url,
            args=config.args,
        )
        await client.connect()
        self._externals[config.name] = client
        for tool in client.cached_tools:
            self._tool_index[tool.name] = config.name

    async def disconnect(self, name: str) -> None:
        """Disconnect from an external server and remove its tools."""
        if name not in self._externals:
            raise MCPError(
                f"Server '{name}' not connected",
                user_message=f"No external server named '{name}' is connected.",
            )
        client = self._externals.pop(name)
        await client.disconnect()
        self._tool_index = {k: v for k, v in self._tool_index.items() if v != name}

    # ── queries ────────────────────────────────────────────────────────────────

    def list_servers(self) -> list[MCPServerInfo]:
        """Return metadata for all registered servers (built-in + external)."""
        result: list[MCPServerInfo] = []
        for s in self._builtins.values():
            result.append(
                MCPServerInfo(
                    name=s.name,
                    kind="builtin",
                    transport="builtin",
                    connected=True,
                    tool_count=len(s.list_tools()),
                    description=s.description,
                )
            )
        for name, client in self._externals.items():
            result.append(
                MCPServerInfo(
                    name=name,
                    kind="external",
                    transport=client.transport,
                    connected=client.is_connected,
                    tool_count=client.tool_count,
                    command=client._command,
                    url=client._url,
                )
            )
        return result

    def list_tools(self) -> list[MCPTool]:
        """Return all tools from all registered servers."""
        tools: list[MCPTool] = []
        for s in self._builtins.values():
            tools.extend(s.list_tools())
        for client in self._externals.values():
            tools.extend(client.cached_tools)
        return tools

    def get_tool(self, name: str) -> MCPTool | None:
        """Find a tool by name across all servers."""
        for tool in self.list_tools():
            if tool.name == name:
                return tool
        return None

    # ── dispatch ───────────────────────────────────────────────────────────────

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPCallResult:
        """Route *tool_name* to the right server and return its result."""
        server_name = self._tool_index.get(tool_name)
        if server_name is None:
            return MCPCallResult(
                tool_name=tool_name,
                server_name="",
                content=f"Unknown tool '{tool_name}'. Use /mcp tools to list available tools.",
                is_error=True,
            )

        if server_name in self._builtins:
            return await self._builtins[server_name].call_tool(tool_name, arguments)

        if server_name in self._externals:
            return await self._externals[server_name].call_tool(tool_name, arguments)

        return MCPCallResult(
            tool_name=tool_name,
            server_name=server_name,
            content=f"Server '{server_name}' is no longer connected.",
            is_error=True,
        )
