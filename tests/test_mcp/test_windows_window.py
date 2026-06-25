"""Tests for WindowsWindowServer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from anythink.mcp.builtin.windows_window import WindowsWindowServer
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.safety import WindowsSafetyChecker


class TestWindowsWindowServer:
    def _make_server(self, gui_mode: bool = False) -> WindowsWindowServer:
        return WindowsWindowServer(
            safety=MagicMock(spec=WindowsSafetyChecker),
            audit=MagicMock(spec=WindowsAuditLog),
            gui_mode=gui_mode,
        )

    def test_list_tools_count(self) -> None:
        srv = self._make_server()
        assert len(srv.list_tools()) == 7

    def test_list_tools_names(self) -> None:
        srv = self._make_server()
        names = {t.name for t in srv.list_tools()}
        assert names == {
            "list_open_windows",
            "bring_to_foreground",
            "minimize_window",
            "maximize_window",
            "restore_window",
            "close_window",
            "send_text_to_window",
        }

    def test_server_name_on_tools(self) -> None:
        srv = self._make_server()
        for t in srv.list_tools():
            assert t.server_name == "windows-window"

    async def test_non_windows_error(self) -> None:
        srv = self._make_server()
        with patch("anythink.mcp.builtin.windows_window._WINDOWS_ONLY", False):
            result = await srv.call_tool("list_open_windows", {})
        assert "Windows" in result.content

    async def test_send_text_requires_gui_mode(self) -> None:
        srv = self._make_server(gui_mode=False)
        with patch("anythink.mcp.builtin.windows_window._WINDOWS_ONLY", True):
            result = await srv.call_tool("send_text_to_window", {"title": "Test", "text": "hello"})
        assert "gui" in result.content.lower() or "GUI" in result.content

    async def test_send_text_allowed_in_gui_mode(self) -> None:
        srv = self._make_server(gui_mode=True)
        mock_gw = MagicMock()
        mock_win = MagicMock()
        mock_win.title = "Test Window"
        mock_gw.getWindowsWithTitle.return_value = [mock_win]
        mock_pyautogui = MagicMock()
        with (
            patch("anythink.mcp.builtin.windows_window._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"pygetwindow": mock_gw, "pyautogui": mock_pyautogui}),
        ):
            result = await srv.call_tool(
                "send_text_to_window",
                {"title": "Test", "text": "hello", "press_enter": False},
            )
        assert not result.is_error
        mock_pyautogui.typewrite.assert_called_once_with("hello", interval=0.05)

    async def test_list_open_windows_mocked(self) -> None:
        srv = self._make_server()
        mock_gw = MagicMock()
        win1 = MagicMock()
        win1.title = "Notepad"
        win1.isMinimized = False
        win1.isMaximized = False
        mock_gw.getAllWindows.return_value = [win1]
        with (
            patch("anythink.mcp.builtin.windows_window._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"pygetwindow": mock_gw}),
        ):
            result = await srv.call_tool("list_open_windows", {})
        assert not result.is_error
        assert "Notepad" in result.content

    async def test_window_action_missing_pygetwindow(self) -> None:
        srv = self._make_server()
        with (
            patch("anythink.mcp.builtin.windows_window._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"pygetwindow": None}),
        ):
            result = await srv.call_tool("minimize_window", {"title": "Test"})
        # Should get an error about missing pygetwindow or import error
        assert result.is_error or "pygetwindow" in result.content.lower() or "not installed" in result.content.lower()

    async def test_unknown_tool(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("no_tool", {})
        assert result.is_error
