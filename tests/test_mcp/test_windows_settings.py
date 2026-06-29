"""Tests for WindowsSettingsServer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from anythink.mcp.builtin.windows_settings import WindowsSettingsServer
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.safety import WindowsSafetyChecker


class TestWindowsSettingsServer:
    def _make_server(self) -> WindowsSettingsServer:
        return WindowsSettingsServer(
            safety=MagicMock(spec=WindowsSafetyChecker),
            audit=MagicMock(spec=WindowsAuditLog),
        )

    def test_list_tools_count(self) -> None:
        srv = self._make_server()
        assert len(srv.list_tools()) == 11

    def test_list_tools_names(self) -> None:
        srv = self._make_server()
        names = {t.name for t in srv.list_tools()}
        assert "get_volume" in names
        assert "set_volume" in names
        assert "mute_audio" in names
        assert "get_brightness" in names
        assert "set_brightness" in names
        assert "get_power_plan" in names
        assert "list_power_plans" in names
        assert "set_power_plan" in names
        assert "get_timezone" in names
        assert "set_timezone" in names
        assert "get_display_info" in names

    def test_server_name_on_all_tools(self) -> None:
        srv = self._make_server()
        for t in srv.list_tools():
            assert t.server_name == "windows-settings"

    async def test_non_windows_error(self) -> None:
        srv = self._make_server()
        with patch("anythink.mcp.builtin.windows_settings._WINDOWS_ONLY", False):
            result = await srv.call_tool("get_volume", {})
        assert "Windows" in result.content

    async def test_get_power_plan_mocks_subprocess(self) -> None:
        srv = self._make_server()
        mock_run = MagicMock()
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)\n"
        with (
            patch("anythink.mcp.builtin.windows_settings._WINDOWS_ONLY", True),
            patch("anythink.mcp.builtin.windows_settings.subprocess.run", mock_run),
        ):
            result = await srv.call_tool("get_power_plan", {})
        assert not result.is_error

    async def test_get_timezone_mocks_subprocess(self) -> None:
        srv = self._make_server()
        mock_run = MagicMock()
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Pacific Standard Time\n"
        with (
            patch("anythink.mcp.builtin.windows_settings._WINDOWS_ONLY", True),
            patch("anythink.mcp.builtin.windows_settings.subprocess.run", mock_run),
        ):
            result = await srv.call_tool("get_timezone", {})
        assert not result.is_error
        assert "Pacific" in result.content

    async def test_set_timezone_permission_error(self) -> None:
        srv = self._make_server()
        mock_run = MagicMock()
        mock_run.side_effect = PermissionError("Access denied")
        with (
            patch("anythink.mcp.builtin.windows_settings._WINDOWS_ONLY", True),
            patch("anythink.mcp.builtin.windows_settings.subprocess.run", mock_run),
        ):
            result = await srv.call_tool("set_timezone", {"timezone": "Eastern Standard Time"})
        assert "privilege" in result.content.lower() or "admin" in result.content.lower() or "permission" in result.content.lower()

    async def test_set_power_plan_no_match(self) -> None:
        srv = self._make_server()
        mock_run = MagicMock()
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Power Scheme GUID: aaa  (Balanced)\n"
        with (
            patch("anythink.mcp.builtin.windows_settings._WINDOWS_ONLY", True),
            patch("anythink.mcp.builtin.windows_settings.subprocess.run", mock_run),
        ):
            result = await srv.call_tool("set_power_plan", {"name": "UltraPerformance"})
        assert "not found" in result.content.lower() or "no power plan" in result.content.lower()

    async def test_unknown_tool(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("frobnicate", {})
        assert result.is_error
