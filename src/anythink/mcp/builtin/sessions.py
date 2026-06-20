"""Built-in MCP Sessions server: list and retrieve saved sessions."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool

if TYPE_CHECKING:
    from anythink.session.manager import SessionManager

_MAX_MESSAGES = 20


class SessionsServer(BuiltinMCPServer):
    """Exposes saved Anythink sessions as MCP tools."""

    name = "sessions"
    description = "List and retrieve saved Anythink conversation sessions."

    def __init__(self, session_manager: SessionManager) -> None:
        self._sm = session_manager

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="list_sessions",
                description="List all saved sessions with their IDs, names, and message counts.",
                input_schema={},
                server_name=self.name,
            ),
            MCPTool(
                name="get_session",
                description="Retrieve messages from a session by ID or name.",
                input_schema={
                    "id_or_name": {"type": "string", "description": "Session ID or name"},
                    "last_n": {
                        "type": "integer",
                        "description": "Max messages to return",
                        "default": _MAX_MESSAGES,
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
        if name == "list_sessions":
            return self._list_sessions()
        if name == "get_session":
            last_n = int(arguments.get("last_n", _MAX_MESSAGES))
            return self._get_session(str(arguments.get("id_or_name", "")), last_n)
        raise ValueError(f"Unknown tool '{name}'")

    def _list_sessions(self) -> str:
        sessions = self._sm.list_sessions()
        if not sessions:
            return "No saved sessions."
        lines = [f"{'ID':>10}  {'Messages':>8}  Name"]
        lines.append("-" * 40)
        for s in sessions:
            name_part = s.name or "(unnamed)"
            lines.append(f"{s.id[:8]:>10}  {len(s.messages):>8}  {name_part}")
        return "\n".join(lines)

    def _get_session(self, id_or_name: str, last_n: int) -> str:
        if not id_or_name:
            raise ValueError("id_or_name is required")
        session = self._sm.find_by_name_or_id(id_or_name)
        if session is None:
            raise KeyError(f"Session '{id_or_name}' not found")
        msgs = session.messages[-last_n:]
        lines: list[str] = []
        for m in msgs:
            role = m.role.upper()
            content = str(m.content)[:300] + ("…" if len(str(m.content)) > 300 else "")
            lines.append(f"[{role}] {content}")
        return "\n".join(lines) or "(empty session)"
