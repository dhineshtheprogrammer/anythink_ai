"""Abstract base for built-in MCP servers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from anythink.mcp.models import MCPCallResult, MCPTool


class BuiltinMCPServer(ABC):
    """A pure-Python MCP server that requires no SDK or network transport.

    Each subclass registers tools via ``list_tools()`` and dispatches
    calls via ``call_tool()``.
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def list_tools(self) -> list[MCPTool]:
        """Return the tools this server exposes."""

    @abstractmethod
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        """Invoke *name* with *arguments* and return a result."""
