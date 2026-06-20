"""MCP data models: tool definitions, call results, and server metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPTool:
    """A tool exposed by an MCP server (built-in or external)."""

    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str


@dataclass
class MCPCallResult:
    """Outcome of calling an MCP tool."""

    tool_name: str
    server_name: str
    content: str
    is_error: bool = False
    duration_s: float = 0.0


@dataclass
class MCPServerInfo:
    """Snapshot metadata for one MCP server."""

    name: str
    kind: str  # "builtin" | "external"
    transport: str  # "builtin" | "stdio" | "sse"
    connected: bool = True
    tool_count: int = 0
    command: str = ""
    url: str = ""
    description: str = ""


@dataclass
class MCPConnectConfig:
    """Parameters for connecting to an external MCP server."""

    name: str
    transport: str  # "stdio" | "sse"
    command: str = ""  # used for stdio
    url: str = ""  # used for sse
    args: list[str] = field(default_factory=list)
