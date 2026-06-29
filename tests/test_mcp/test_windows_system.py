"""Tests for WindowsSystemServer."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from anythink.mcp.builtin.windows_system import WindowsSystemServer
from anythink.mcp.windows.audit import WindowsAuditLog


class TestWindowsSystemServer:
    def _make_server(self, tmp_path: Path) -> WindowsSystemServer:
        audit = MagicMock(spec=WindowsAuditLog)
        return WindowsSystemServer(audit=audit)

    def test_list_tools_count(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        tools = srv.list_tools()
        assert len(tools) == 8

    def test_list_tools_names(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        names = {t.name for t in srv.list_tools()}
        expected = {
            "get_cpu_info",
            "get_ram_info",
            "get_disk_info",
            "get_battery_info",
            "get_network_info",
            "get_windows_version",
            "get_hardware_info",
            "get_installed_apps",
        }
        assert names == expected

    def test_list_tools_server_name(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        for t in srv.list_tools():
            assert t.server_name == "windows-system"

    async def test_non_windows_returns_platform_message(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        with patch("sys.platform", "linux"):
            # Rebuild _WINDOWS_ONLY state by patching the module attribute
            with patch("anythink.mcp.builtin.windows_system._WINDOWS_ONLY", False):
                result = await srv.call_tool("get_cpu_info", {})
        assert not result.is_error  # returns message, not exception
        assert "Windows" in result.content or "platform" in result.content.lower()

    async def test_unknown_tool_returns_error(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        result = await srv.call_tool("nonexistent_tool", {})
        assert result.is_error

    async def test_get_windows_version_safe(self, tmp_path: Path) -> None:
        """get_windows_version uses only stdlib — safe to call on any platform."""
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_system._WINDOWS_ONLY", True):
            result = await srv.call_tool("get_windows_version", {})
        # On non-Windows sys.getwindowsversion() raises AttributeError — handled gracefully
        assert result.tool_name == "get_windows_version"
        assert result.server_name == "windows-system"
        assert not result.is_error or "unknown" in result.content.lower()

    async def test_get_cpu_info_mock_psutil(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        mock_psutil = MagicMock()
        mock_psutil.cpu_count.return_value = 4
        # cpu_percent is called twice: once overall (returns float), once percpu (returns list)
        mock_psutil.cpu_percent.side_effect = [12.3, [10.0, 20.0, 5.0, 8.0]]
        mock_psutil.cpu_freq.return_value = MagicMock(current=2400.0, max=4000.0)
        with (
            patch("anythink.mcp.builtin.windows_system._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"psutil": mock_psutil}),
        ):
            result = await srv.call_tool("get_cpu_info", {})
        assert not result.is_error
        assert result.server_name == "windows-system"

    async def test_get_ram_info_mock_psutil(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        mock_psutil = MagicMock()
        vm = MagicMock()
        vm.total = 16 * (1024 ** 3)
        vm.used = 8 * (1024 ** 3)
        vm.available = 8 * (1024 ** 3)
        vm.percent = 50.0
        swap = MagicMock()
        swap.total = 4 * (1024 ** 3)
        swap.used = 1 * (1024 ** 3)
        mock_psutil.virtual_memory.return_value = vm
        mock_psutil.swap_memory.return_value = swap
        with (
            patch("anythink.mcp.builtin.windows_system._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"psutil": mock_psutil}),
        ):
            result = await srv.call_tool("get_ram_info", {})
        assert not result.is_error
        assert "50" in result.content  # percent

    async def test_audit_log_called(self, tmp_path: Path) -> None:
        audit = MagicMock(spec=WindowsAuditLog)
        srv = WindowsSystemServer(audit=audit)
        with patch("anythink.mcp.builtin.windows_system._WINDOWS_ONLY", False):
            await srv.call_tool("get_cpu_info", {})
        audit.log.assert_called_once()
