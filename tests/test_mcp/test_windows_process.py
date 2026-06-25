"""Tests for WindowsProcessServer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from anythink.mcp.builtin.windows_process import WindowsProcessServer
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.safety import WindowsSafetyChecker


class TestWindowsProcessServer:
    def _make_server(self) -> WindowsProcessServer:
        return WindowsProcessServer(
            safety=MagicMock(spec=WindowsSafetyChecker),
            audit=MagicMock(spec=WindowsAuditLog),
        )

    def test_list_tools(self) -> None:
        srv = self._make_server()
        names = {t.name for t in srv.list_tools()}
        assert names == {"list_processes", "get_process_info", "start_process", "kill_process"}
        for t in srv.list_tools():
            assert t.server_name == "windows-process"

    async def test_non_windows_error(self) -> None:
        srv = self._make_server()
        with patch("anythink.mcp.builtin.windows_process._WINDOWS_ONLY", False):
            result = await srv.call_tool("list_processes", {})
        assert "Windows" in result.content

    async def test_list_processes_mocked(self) -> None:
        srv = self._make_server()
        mock_psutil = MagicMock()
        proc = MagicMock()
        proc.info = {"pid": 1234, "name": "test.exe", "cpu_percent": 5.0, "memory_percent": 1.0, "status": "running"}
        mock_psutil.process_iter.return_value = [proc]
        with (
            patch("anythink.mcp.builtin.windows_process._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"psutil": mock_psutil}),
        ):
            result = await srv.call_tool("list_processes", {})
        assert not result.is_error
        assert "test.exe" in result.content

    async def test_start_process_blocked_app_rejected(self) -> None:
        srv = WindowsProcessServer(
            safety=MagicMock(spec=WindowsSafetyChecker),
            audit=MagicMock(spec=WindowsAuditLog),
            blocked_apps=("regedit.exe", "cmd.exe"),
        )
        with patch("anythink.mcp.builtin.windows_process._WINDOWS_ONLY", True):
            result = await srv.call_tool("start_process", {"command": "C:\\Windows\\regedit.exe"})
        assert "blocked" in result.content.lower()

    async def test_kill_process_protected_system_account(self) -> None:
        srv = self._make_server()
        mock_psutil = MagicMock()
        proc = MagicMock()
        proc.pid = 4
        proc.name.return_value = "System"
        proc.username.return_value = "NT AUTHORITY\\SYSTEM"
        mock_psutil.Process.return_value = proc
        with (
            patch("anythink.mcp.builtin.windows_process._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"psutil": mock_psutil}),
        ):
            result = await srv.call_tool("kill_process", {"pid": 4})
        assert "protected" in result.content.lower()
        proc.terminate.assert_not_called()

    async def test_get_process_info_no_pid_or_name(self) -> None:
        srv = self._make_server()
        with patch("anythink.mcp.builtin.windows_process._WINDOWS_ONLY", True):
            mock_psutil = MagicMock()
            with patch.dict("sys.modules", {"psutil": mock_psutil}):
                result = await srv.call_tool("get_process_info", {})
        assert "pid" in result.content.lower() or "name" in result.content.lower()

    async def test_kill_process_missing_psutil(self) -> None:
        srv = self._make_server()
        with (
            patch("anythink.mcp.builtin.windows_process._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"psutil": None}),
        ):
            result = await srv.call_tool("kill_process", {"pid": 1})
        assert "psutil" in result.content.lower() or not result.is_error  # returns message

    async def test_unknown_tool(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("noop", {})
        assert result.is_error
