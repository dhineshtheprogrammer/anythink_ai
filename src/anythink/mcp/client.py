"""MCPClient: connects to external MCP servers via stdio or SSE transport.

Requires ``pip install anythink[mcp]`` for actual connections.
The mcp SDK is imported lazily so the rest of Anythink works without it.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from anythink.exceptions import MCPError
from anythink.mcp.models import MCPCallResult, MCPTool


class MCPClient:
    """Connects to one external MCP server and proxies tool calls."""

    def __init__(
        self,
        name: str,
        transport: str,
        *,
        command: str = "",
        url: str = "",
        args: list[str] | None = None,
    ) -> None:
        self.name = name
        self.transport = transport
        self._command = command
        self._url = url
        self._args = args or []
        self._tools: list[MCPTool] = []
        self._session: Any = None
        self._exit_stack: contextlib.AsyncExitStack | None = None

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def cached_tools(self) -> list[MCPTool]:
        return list(self._tools)

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    async def connect(self) -> None:
        """Open the transport and initialise the MCP session."""
        try:
            from mcp import ClientSession
        except ImportError as exc:
            raise MCPError(
                "mcp SDK not installed",
                user_message="External MCP servers require: pip install anythink[mcp]",
            ) from exc

        stack = contextlib.AsyncExitStack()

        if self.transport == "stdio":
            try:
                from mcp import StdioServerParameters
                from mcp.client.stdio import stdio_client
            except ImportError as exc:
                await stack.aclose()
                raise MCPError(
                    "mcp stdio transport not available",
                    user_message="stdio transport requires: pip install anythink[mcp]",
                ) from exc

            cmd_parts = self._command.split() if self._command else []
            if not cmd_parts:
                raise MCPError("command is required for stdio transport")
            params = StdioServerParameters(command=cmd_parts[0], args=cmd_parts[1:] + self._args)
            read, write = await stack.enter_async_context(stdio_client(params))

        elif self.transport == "sse":
            try:
                from mcp.client.sse import sse_client
            except ImportError as exc:
                await stack.aclose()
                raise MCPError(
                    "mcp SSE transport not available",
                    user_message="SSE transport requires: pip install anythink[mcp]",
                ) from exc

            if not self._url:
                raise MCPError("url is required for sse transport")
            read, write = await stack.enter_async_context(sse_client(self._url))

        else:
            await stack.aclose()
            raise MCPError(
                f"Unknown transport '{self.transport}'",
                user_message=f"Unsupported MCP transport '{self.transport}'. Use stdio or sse.",
            )

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session
        self._exit_stack = stack

        response = await session.list_tools()
        self._tools = [
            MCPTool(
                name=t.name,
                description=t.description or "",
                input_schema=dict(t.inputSchema) if t.inputSchema else {},
                server_name=self.name,
            )
            for t in response.tools
        ]

    async def disconnect(self) -> None:
        """Close the transport and clean up."""
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
        self._session = None
        self._tools = []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        """Call *name* with *arguments* on the connected server."""
        if self._session is None:
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content="Not connected to server.",
                is_error=True,
            )

        t0 = time.monotonic()
        try:
            result = await self._session.call_tool(name, arguments)
        except Exception as exc:
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content=str(exc),
                is_error=True,
                duration_s=round(time.monotonic() - t0, 3),
            )

        content_parts: list[str] = []
        if result.content:
            for item in result.content:
                if hasattr(item, "text"):
                    content_parts.append(str(item.text))

        return MCPCallResult(
            tool_name=name,
            server_name=self.name,
            content="\n".join(content_parts),
            is_error=bool(getattr(result, "isError", False)),
            duration_s=round(time.monotonic() - t0, 3),
        )
