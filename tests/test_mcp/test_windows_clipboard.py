"""Tests for WindowsClipboardServer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

from anythink.mcp.builtin.windows_clipboard import WindowsClipboardServer, _1MB
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.safety import WindowsSafetyChecker


class TestWindowsClipboardServer:
    def _make_server(self) -> WindowsClipboardServer:
        return WindowsClipboardServer(
            safety=MagicMock(spec=WindowsSafetyChecker),
            audit=MagicMock(spec=WindowsAuditLog),
        )

    def test_list_tools(self) -> None:
        srv = self._make_server()
        tools = srv.list_tools()
        names = {t.name for t in tools}
        assert names == {"read_clipboard", "write_clipboard", "clear_clipboard"}
        for t in tools:
            assert t.server_name == "windows-clipboard"

    async def test_non_windows_error(self) -> None:
        srv = self._make_server()
        with patch("anythink.mcp.builtin.windows_clipboard._WINDOWS_ONLY", False):
            result = await srv.call_tool("read_clipboard", {})
        assert "Windows" in result.content

    async def test_read_clipboard_missing_pywin32(self) -> None:
        srv = self._make_server()
        with (
            patch("anythink.mcp.builtin.windows_clipboard._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"win32clipboard": None, "win32con": None}),
        ):
            result = await srv.call_tool("read_clipboard", {})
        assert "pywin32" in result.content.lower() or "not installed" in result.content.lower()

    async def test_read_clipboard_success(self) -> None:
        srv = self._make_server()
        mock_clip = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13
        mock_clip.IsClipboardFormatAvailable.return_value = True
        mock_clip.GetClipboardData.return_value = "hello world"
        with (
            patch("anythink.mcp.builtin.windows_clipboard._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"win32clipboard": mock_clip, "win32con": mock_con}),
        ):
            result = await srv.call_tool("read_clipboard", {})
        assert not result.is_error
        assert "hello world" in result.content
        # CloseClipboard must be called even on success
        mock_clip.CloseClipboard.assert_called_once()

    async def test_read_clipboard_always_closes(self) -> None:
        """CloseClipboard must be called even when GetClipboardData raises."""
        srv = self._make_server()
        mock_clip = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13
        mock_clip.IsClipboardFormatAvailable.return_value = True
        mock_clip.GetClipboardData.side_effect = OSError("clipboard busy")
        with (
            patch("anythink.mcp.builtin.windows_clipboard._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"win32clipboard": mock_clip, "win32con": mock_con}),
        ):
            result = await srv.call_tool("read_clipboard", {})
        assert result.is_error
        mock_clip.CloseClipboard.assert_called_once()

    async def test_write_clipboard_size_cap(self) -> None:
        """Text larger than 1 MB (UTF-16-LE) is rejected."""
        srv = self._make_server()
        huge_text = "X" * (_1MB + 100)  # well over 1 MB in UTF-16-LE
        with (
            patch("anythink.mcp.builtin.windows_clipboard._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"win32clipboard": MagicMock(), "win32con": MagicMock()}),
        ):
            result = await srv.call_tool("write_clipboard", {"text": huge_text})
        assert "too large" in result.content.lower() or "maximum" in result.content.lower()

    async def test_write_clipboard_success(self) -> None:
        srv = self._make_server()
        mock_clip = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13
        with (
            patch("anythink.mcp.builtin.windows_clipboard._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"win32clipboard": mock_clip, "win32con": mock_con}),
        ):
            result = await srv.call_tool("write_clipboard", {"text": "hello"})
        assert not result.is_error
        assert "5" in result.content  # 5 characters
        mock_clip.CloseClipboard.assert_called_once()

    async def test_clear_clipboard(self) -> None:
        srv = self._make_server()
        mock_clip = MagicMock()
        with (
            patch("anythink.mcp.builtin.windows_clipboard._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"win32clipboard": mock_clip, "win32con": MagicMock()}),
        ):
            result = await srv.call_tool("clear_clipboard", {})
        assert not result.is_error
        mock_clip.EmptyClipboard.assert_called_once()
        mock_clip.CloseClipboard.assert_called_once()

    async def test_unknown_tool_error(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("no_such_tool", {})
        assert result.is_error
