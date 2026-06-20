"""Built-in MCP Filesystem server: list_dir and read_file."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool

_MAX_READ_CHARS = 8_000


class FilesystemServer(BuiltinMCPServer):
    """Exposes basic filesystem operations as MCP tools."""

    name = "filesystem"
    description = "Read and list local files."

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="list_dir",
                description="List files and directories at the given path.",
                input_schema={"path": {"type": "string", "description": "Directory path"}},
                server_name=self.name,
            ),
            MCPTool(
                name="read_file",
                description="Read a text file and return its content.",
                input_schema={
                    "path": {"type": "string", "description": "File path"},
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to return",
                        "default": _MAX_READ_CHARS,
                    },
                },
                server_name=self.name,
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        t0 = time.monotonic()
        try:
            content = await self._dispatch(name, arguments)
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content=content,
                duration_s=round(time.monotonic() - t0, 3),
            )
        except Exception as exc:
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content=str(exc),
                is_error=True,
                duration_s=round(time.monotonic() - t0, 3),
            )

    async def _dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "list_dir":
            return self._list_dir(str(arguments.get("path", ".")))
        if name == "read_file":
            max_chars = int(arguments.get("max_chars", _MAX_READ_CHARS))
            return self._read_file(str(arguments.get("path", "")), max_chars)
        raise ValueError(f"Unknown tool '{name}'")

    def _list_dir(self, path: str) -> str:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Path not found: {p}")
        if p.is_file():
            return str(p)
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        lines = [f"{'[D]' if e.is_dir() else '[F]'} {e.name}" for e in entries]
        return f"{p}\n" + "\n".join(lines)

    def _read_file(self, path: str, max_chars: int) -> str:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        if not p.is_file():
            raise IsADirectoryError(f"Not a file: {p}")
        text = p.read_text(encoding="utf-8", errors="replace")
        suffix = f"\n[truncated at {max_chars} chars]" if len(text) > max_chars else ""
        return text[:max_chars] + suffix
