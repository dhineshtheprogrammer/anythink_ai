"""Built-in MCP RAG server: search the active vector index."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool

if TYPE_CHECKING:
    from anythink.embeddings.base import BaseEmbeddingBackend
    from anythink.rag.manager import RAGManager


class RAGServer(BuiltinMCPServer):
    """Exposes the active RAG index as an MCP search tool."""

    name = "rag"
    description = "Search the active RAG index for relevant content."

    def __init__(
        self,
        rag_manager: RAGManager,
        embedding_backend: BaseEmbeddingBackend | None = None,
    ) -> None:
        self._rag = rag_manager
        self._emb = embedding_backend

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="rag_search",
                description="Search the active RAG index and return the most relevant chunks.",
                input_schema={
                    "query": {"type": "string", "description": "Search query"},
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5,
                    },
                },
                server_name=self.name,
            )
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        t0 = time.monotonic()
        if name != "rag_search":
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content=f"Unknown tool '{name}'",
                is_error=True,
            )

        if not self._rag.is_active:
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content="No RAG index is active. Use /rag use <name> to activate one.",
                is_error=True,
                duration_s=round(time.monotonic() - t0, 3),
            )

        if self._emb is None:
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content="No embedding backend available. Install anythink[rag].",
                is_error=True,
                duration_s=round(time.monotonic() - t0, 3),
            )

        query = str(arguments.get("query", ""))
        top_k = int(arguments.get("top_k", 5))

        try:
            results = await self._rag.retrieve(query, self._emb, top_k=top_k)
        except Exception as exc:
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content=f"Retrieval failed: {exc}",
                is_error=True,
                duration_s=round(time.monotonic() - t0, 3),
            )

        if not results:
            content = "No results found."
        else:
            parts = [
                f"[{r.source_path}]\n{r.chunk_text}\n(relevance: {r.relevance:.3f})"
                for r in results
            ]
            content = "\n\n---\n\n".join(parts)

        return MCPCallResult(
            tool_name=name,
            server_name=self.name,
            content=content,
            duration_s=round(time.monotonic() - t0, 3),
        )
