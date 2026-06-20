"""Built-in MCP Web Search server: search the web via SearchRegistry."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool

if TYPE_CHECKING:
    from anythink.search.registry import SearchRegistry


class SearchServer(BuiltinMCPServer):
    """Exposes web search as an MCP tool."""

    name = "search"
    description = "Search the web using the configured search backend."

    def __init__(self, search_registry: SearchRegistry, preferred: str = "duckduckgo") -> None:
        self._registry = search_registry
        self._preferred = preferred

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="web_search",
                description="Search the web and return titles, URLs, and snippets.",
                input_schema={
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 5,
                    },
                },
                server_name=self.name,
            )
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        t0 = time.monotonic()
        if name != "web_search":
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content=f"Unknown tool '{name}'",
                is_error=True,
            )

        backend = self._registry.get_available(self._preferred)
        if backend is None:
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content="No search backend available. Install anythink[search].",
                is_error=True,
                duration_s=round(time.monotonic() - t0, 3),
            )

        query = str(arguments.get("query", ""))
        max_results = int(arguments.get("max_results", 5))

        try:
            results = await backend.search(query)
        except Exception as exc:
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content=f"Search failed: {exc}",
                is_error=True,
                duration_s=round(time.monotonic() - t0, 3),
            )

        if not results:
            content = f"No results for '{query}'."
        else:
            lines: list[str] = []
            for r in results[:max_results]:
                lines.append(f"{r.title}\n{r.url}")
                if r.snippet:
                    lines.append(f"  {r.snippet[:200]}")
            content = "\n\n".join(lines)

        return MCPCallResult(
            tool_name=name,
            server_name=self.name,
            content=content,
            duration_s=round(time.monotonic() - t0, 3),
        )
