"""Tests for WindowsAppsServer."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from anythink.mcp.builtin.windows_apps import WindowsAppsServer
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.safety import WindowsSafetyChecker


class TestWindowsAppsServer:
    def _make_server(
        self,
        blocked_apps: tuple[str, ...] = ("regedit.exe", "cmd.exe"),
        cache_ttl_minutes: int = 60,
    ) -> WindowsAppsServer:
        return WindowsAppsServer(
            safety=MagicMock(spec=WindowsSafetyChecker),
            audit=MagicMock(spec=WindowsAuditLog),
            blocked_apps=blocked_apps,
            cache_ttl_minutes=cache_ttl_minutes,
        )

    def test_list_tools(self) -> None:
        srv = self._make_server()
        names = {t.name for t in srv.list_tools()}
        assert names == {"list_installed_apps", "launch_app"}
        for t in srv.list_tools():
            assert t.server_name == "windows-apps"

    async def test_non_windows_error(self) -> None:
        srv = self._make_server()
        with patch("anythink.mcp.builtin.windows_apps._WINDOWS_ONLY", False):
            result = await srv.call_tool("list_installed_apps", {})
        assert "Windows" in result.content

    async def test_cache_populated_after_first_call(self) -> None:
        srv = self._make_server()
        srv._cache = [{"name": "Notepad", "exe": "C:\\Windows\\notepad.exe"}]
        srv._cache_time = time.monotonic()
        with patch("anythink.mcp.builtin.windows_apps._WINDOWS_ONLY", True):
            result = await srv.call_tool("list_installed_apps", {})
        assert not result.is_error
        assert "Notepad" in result.content

    async def test_cache_ttl_expiry(self) -> None:
        srv = self._make_server(cache_ttl_minutes=0)  # TTL of 0 → always expired
        srv._cache = [{"name": "OldApp", "exe": "C:\\old.exe"}]
        srv._cache_time = 0.0  # expired

        mock_discover = MagicMock(return_value=[{"name": "NewApp", "exe": "C:\\new.exe"}])
        with (
            patch("anythink.mcp.builtin.windows_apps._WINDOWS_ONLY", True),
            patch.object(srv, "_discover_apps", mock_discover),
        ):
            result = await srv.call_tool("list_installed_apps", {})
        mock_discover.assert_called_once()
        assert "NewApp" in result.content

    async def test_launch_blocked_app_rejected(self) -> None:
        srv = self._make_server(blocked_apps=("regedit.exe", "cmd.exe"))
        srv._cache = [{"name": "Registry Editor", "exe": "C:\\Windows\\regedit.exe"}]
        srv._cache_time = time.monotonic()
        with patch("anythink.mcp.builtin.windows_apps._WINDOWS_ONLY", True):
            result = await srv.call_tool("launch_app", {"name": "Registry Editor"})
        assert "blocked" in result.content.lower()

    async def test_launch_fuzzy_cutoff_06(self) -> None:
        """Tests that a very poor match (below 0.6) produces no result from fuzzy matching."""
        import difflib
        names = ["Microsoft Word", "Microsoft Excel", "Microsoft PowerPoint"]
        # "xyz" should not match at 0.6 cutoff
        close = difflib.get_close_matches("xyz", names, n=3, cutoff=0.6)
        assert close == [], "Fuzzy match with cutoff=0.6 should not match 'xyz'"

    async def test_launch_no_match_returns_not_found(self) -> None:
        srv = self._make_server()
        srv._cache = [{"name": "Notepad", "exe": "C:\\Windows\\notepad.exe"}]
        srv._cache_time = time.monotonic()
        with patch("anythink.mcp.builtin.windows_apps._WINDOWS_ONLY", True):
            result = await srv.call_tool("launch_app", {"name": "xyzzy_nonexistent"})
        assert "not found" in result.content.lower() or "no application" in result.content.lower()

    def test_invalidate_cache(self) -> None:
        srv = self._make_server()
        srv._cache = [{"name": "Test", "exe": "test.exe"}]
        srv._cache_time = time.monotonic()
        srv.invalidate_cache()
        assert srv._cache is None
        assert srv._cache_time == 0.0

    async def test_unknown_tool(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("frobnicate", {})
        assert result.is_error
