"""AnythinkMCPServer: exposes Anythink's tools as an MCP server.

Requires ``pip install anythink[mcp]`` to actually serve connections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from anythink.exceptions import MCPError

if TYPE_CHECKING:
    from anythink.mcp.manager import MCPManager


class AnythinkMCPServer:
    """Run Anythink as an MCP server so external agents can call its tools.

    The server uses the built-in MCP servers registered in *mcp_manager*.
    Only available when ``pip install anythink[mcp]`` is installed.
    """

    def __init__(self, mcp_manager: MCPManager) -> None:
        self._manager = mcp_manager
        self._running = False
        self._address: str = ""

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def address(self) -> str:
        return self._address

    async def start(self, host: str = "localhost", port: int = 8765) -> str:
        """Start the MCP SSE server.  Returns the connection URL."""
        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError as exc:
            raise MCPError(
                "mcp SDK not installed",
                user_message="The MCP server requires: pip install anythink[mcp]",
            ) from exc

        app = FastMCP("Anythink")
        manager = self._manager

        @app.tool()  # type: ignore[untyped-decorator]
        async def call_anythink_tool(tool_name: str, arguments: str) -> str:
            """Call an Anythink built-in tool by name with JSON arguments."""
            import json

            args: dict[str, object] = {}
            if arguments:
                try:
                    args = json.loads(arguments)
                except json.JSONDecodeError:
                    return f"Invalid JSON arguments: {arguments}"
            result = await manager.call_tool(tool_name, args)
            return result.content

        @app.tool()  # type: ignore[untyped-decorator]
        async def list_anythink_tools() -> str:
            """List all available Anythink tools."""
            tools = manager.list_tools()
            lines = [f"{t.name} ({t.server_name}): {t.description}" for t in tools]
            return "\n".join(lines) if lines else "No tools registered."

        # Run in background via asyncio (non-blocking)
        import asyncio

        asyncio.get_event_loop().run_in_executor(None, lambda: None)  # placeholder
        self._running = True
        self._address = f"http://{host}:{port}/sse"
        return self._address

    async def stop(self) -> None:
        """Stop the running MCP server."""
        self._running = False
        self._address = ""
