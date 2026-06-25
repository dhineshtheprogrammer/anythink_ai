"""Integration tests for all 10 Windows MCP servers — tool count, routing, platform guard."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anythink.config.schema import AppConfig
from anythink.mcp.manager import MCPManager
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.paths import WindowsPathGuard
from anythink.mcp.windows.safety import WindowsSafetyChecker

# Sentinel — expected total tool count across all 10 Windows servers
_EXPECTED_TOOL_COUNT = 59


def _make_deps(tmp_path: Path):  # type: ignore[return]
    config = AppConfig(
        windows_allowed_paths=(str(tmp_path) + os.sep,),
        windows_blocked_paths=(),
    )
    audit = WindowsAuditLog(str(tmp_path / "audit.log"))
    path_guard = WindowsPathGuard(config)
    safety = WindowsSafetyChecker()
    return config, audit, path_guard, safety


def _build_all_servers(tmp_path: Path) -> list:  # type: ignore[type-arg]
    """Instantiate all 10 Windows servers with real infrastructure (no Windows API calls)."""
    from anythink.mcp.builtin.windows_apps import WindowsAppsServer
    from anythink.mcp.builtin.windows_clipboard import WindowsClipboardServer
    from anythink.mcp.builtin.windows_explorer import WindowsExplorerServer
    from anythink.mcp.builtin.windows_filesystem import WindowsFilesystemServer
    from anythink.mcp.builtin.windows_notification import WindowsNotificationServer
    from anythink.mcp.builtin.windows_process import WindowsProcessServer
    from anythink.mcp.builtin.windows_screenshot import WindowsScreenshotServer
    from anythink.mcp.builtin.windows_settings import WindowsSettingsServer
    from anythink.mcp.builtin.windows_system import WindowsSystemServer
    from anythink.mcp.builtin.windows_window import WindowsWindowServer

    config, audit, path_guard, safety = _make_deps(tmp_path)
    return [
        WindowsFilesystemServer(path_guard, safety, audit),
        WindowsExplorerServer(path_guard, safety, audit),
        WindowsAppsServer(safety, audit),
        WindowsWindowServer(safety, audit),
        WindowsProcessServer(safety, audit),
        WindowsSystemServer(audit),
        WindowsSettingsServer(safety, audit),
        WindowsClipboardServer(safety, audit),
        WindowsScreenshotServer(safety, audit),
        WindowsNotificationServer(safety, audit),
    ]


class TestWindowsToolRoster:
    def test_all_59_tool_names_unique(self, tmp_path: Path) -> None:
        servers = _build_all_servers(tmp_path)
        all_tools = []
        for srv in servers:
            all_tools.extend(srv.list_tools())
        names = [t.name for t in all_tools]
        assert len(names) == len(set(names)), (
            f"Duplicate tool names: {[n for n in names if names.count(n) > 1]}"
        )

    def test_total_tool_count_is_59(self, tmp_path: Path) -> None:
        servers = _build_all_servers(tmp_path)
        total = sum(len(srv.list_tools()) for srv in servers)
        assert total == _EXPECTED_TOOL_COUNT, (
            f"Expected {_EXPECTED_TOOL_COUNT} tools, got {total}. "
            "Update _EXPECTED_TOOL_COUNT if the spec changed."
        )

    def test_all_tools_have_correct_server_name(self, tmp_path: Path) -> None:
        servers = _build_all_servers(tmp_path)
        for srv in servers:
            for tool in srv.list_tools():
                assert tool.server_name == srv.name, (
                    f"Tool '{tool.name}' has server_name='{tool.server_name}' "
                    f"but expected '{srv.name}'"
                )

    def test_mcp_manager_indexes_all_windows_tools(self, tmp_path: Path) -> None:
        servers = _build_all_servers(tmp_path)
        mgr = MCPManager(builtin_servers=servers)  # type: ignore[arg-type]
        tools = mgr.list_tools()
        win_tools = [t for t in tools if t.server_name.startswith("windows-")]
        assert len(win_tools) == _EXPECTED_TOOL_COUNT


class TestPlatformGuard:
    def test_returns_empty_on_non_windows(self, tmp_path: Path) -> None:
        from anythink.app.context import _build_windows_servers
        from anythink.config.manager import _resolve_paths

        config = AppConfig(windows_enabled=True)
        paths = _resolve_paths()

        with patch("sys.platform", "linux"):
            result = _build_windows_servers(config, paths)
        assert result == []

    def test_returns_empty_when_disabled(self, tmp_path: Path) -> None:
        from anythink.app.context import _build_windows_servers
        from anythink.config.manager import _resolve_paths

        config = AppConfig(windows_enabled=False)
        paths = _resolve_paths()

        with patch("sys.platform", "win32"):
            result = _build_windows_servers(config, paths)
        assert result == []

    def test_returns_10_servers_on_windows_enabled(self, tmp_path: Path) -> None:
        from anythink.app.context import _build_windows_servers
        from anythink.config.manager import Paths

        config = AppConfig(
            windows_enabled=True,
            windows_allowed_paths=(str(tmp_path) + os.sep,),
        )
        paths = Paths(
            config_dir=tmp_path,
            data_dir=tmp_path,
            state_dir=tmp_path,
            cache_dir=tmp_path,
        )
        with patch("sys.platform", "win32"):
            result = _build_windows_servers(config, paths)
        assert len(result) == 10


class TestAuditLogWrittenOnCall:
    async def test_audit_written_on_system_call(self, tmp_path: Path) -> None:
        from anythink.mcp.builtin.windows_system import WindowsSystemServer

        audit = WindowsAuditLog(str(tmp_path / "audit.log"))
        srv = WindowsSystemServer(audit)

        # Call list_tools just to exercise without hitting Windows APIs
        tools = srv.list_tools()
        assert len(tools) == 8

        # Calling get_windows_version is safe even on non-Windows (returns platform error)
        result = await srv.call_tool("get_windows_version", {})
        # On non-Windows it returns the "requires Windows" message but doesn't error fatally
        assert result.tool_name == "get_windows_version"
        assert result.server_name == "windows-system"

        # Audit log should have a record
        records = audit.get_recent(n=5)
        if sys.platform == "win32":
            # On Windows the call succeeds; on other platforms it returns early
            assert len(records) >= 1
        else:
            assert len(records) >= 1  # still logged even when returning platform error


class TestFilesystemServerToolNames:
    def test_13_tools(self, tmp_path: Path) -> None:
        from anythink.mcp.builtin.windows_filesystem import (
            WindowsFilesystemServer,
            _TOOL_NAMES,
        )

        config, audit, path_guard, safety = _make_deps(tmp_path)
        srv = WindowsFilesystemServer(path_guard, safety, audit)
        tools = {t.name for t in srv.list_tools()}
        assert tools == _TOOL_NAMES
        assert len(tools) == 13
