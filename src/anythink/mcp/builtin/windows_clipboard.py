"""Windows Clipboard MCP server — read and write the system clipboard."""

from __future__ import annotations

import sys
import time
from typing import Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.safety import WindowsSafetyChecker

_WINDOWS_ONLY = sys.platform == "win32"
_WIN_ERR = f"This tool requires Windows. Current platform: {sys.platform}"
_1MB = 1_048_576  # max clipboard write size in UTF-16-LE bytes


class WindowsClipboardServer(BuiltinMCPServer):
    """Read from and write to the Windows clipboard."""

    name = "windows-clipboard"
    description = "Read from and write to the Windows clipboard."

    def __init__(self, safety: WindowsSafetyChecker, audit: WindowsAuditLog) -> None:
        self._safety = safety
        self._audit = audit

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                "read_clipboard",
                "Read the current text content of the Windows clipboard.",
                {},
                self.name,
            ),
            MCPTool(
                "write_clipboard",
                "Write text to the Windows clipboard, replacing current contents.",
                {"text": {"type": "string", "description": "Text to write to clipboard"}},
                self.name,
            ),
            MCPTool(
                "clear_clipboard",
                "Clear the clipboard contents.",
                {},
                self.name,
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        t0 = time.monotonic()
        tier = self._safety.get_tier(self.name, name, **arguments)
        try:
            content = self._dispatch(name, arguments)
            outcome = "success"
            error = None
        except Exception as exc:
            content = str(exc)
            outcome = "error"
            error = str(exc)
        duration = round(time.monotonic() - t0, 3)
        self._audit.log(
            session_id="",
            server=self.name,
            tool=name,
            tier=tier,
            arguments={k: v[:100] if isinstance(v, str) else v for k, v in arguments.items()},
            confirmation_status="not_required" if tier == 1 else "auto",
            outcome=outcome,
            duration_s=duration,
            error=error,
        )
        return MCPCallResult(
            tool_name=name,
            server_name=self.name,
            content=content,
            is_error=error is not None,
            duration_s=duration,
        )

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if not _WINDOWS_ONLY:
            return _WIN_ERR
        if name == "read_clipboard":
            return self._read_clipboard()
        if name == "write_clipboard":
            return self._write_clipboard(str(arguments.get("text", "")))
        if name == "clear_clipboard":
            return self._clear_clipboard()
        raise ValueError(f"Unknown tool '{name}'")

    def _read_clipboard(self) -> str:
        try:
            import win32clipboard  # type: ignore[import]
            import win32con  # type: ignore[import]
        except ImportError:
            return "pywin32 not installed. Run: pip install anythink[windows]"

        win32clipboard.OpenClipboard(0)
        try:
            if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                # Try to describe what is on the clipboard
                available = []
                fmt = 0
                while True:
                    fmt = win32clipboard.EnumClipboardFormats(fmt)
                    if fmt == 0:
                        break
                    available.append(fmt)
                if available:
                    return (
                        "Clipboard contains non-text content "
                        f"(format codes: {available}). "
                        "Use /screenshot to capture screen content."
                    )
                return "Clipboard is empty."
            text: str = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return text
        finally:
            win32clipboard.CloseClipboard()

    def _write_clipboard(self, text: str) -> str:
        try:
            import win32clipboard  # type: ignore[import]
            import win32con  # type: ignore[import]
        except ImportError:
            return "pywin32 not installed. Run: pip install anythink[windows]"

        encoded_size = len(text.encode("utf-16-le"))
        if encoded_size > _1MB:
            return (
                f"Text is too large for clipboard ({encoded_size:,} bytes encoded). "
                "Maximum is 1 MB. Consider writing to a file instead."
            )
        win32clipboard.OpenClipboard(0)
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        finally:
            win32clipboard.CloseClipboard()
        return f"Clipboard updated: {len(text):,} characters written."

    def _clear_clipboard(self) -> str:
        try:
            import win32clipboard  # type: ignore[import]
        except ImportError:
            return "pywin32 not installed. Run: pip install anythink[windows]"

        win32clipboard.OpenClipboard(0)
        try:
            win32clipboard.EmptyClipboard()
        finally:
            win32clipboard.CloseClipboard()
        return "Clipboard cleared."
