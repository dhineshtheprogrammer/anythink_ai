"""Tests for WindowsExplorerServer."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from anythink.config.schema import AppConfig
from anythink.mcp.builtin.windows_explorer import WindowsExplorerServer
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.paths import WindowsPathGuard
from anythink.mcp.windows.safety import WindowsSafetyChecker


class TestWindowsExplorerServer:
    def _make_server(self, tmp_path: Path) -> WindowsExplorerServer:
        config = AppConfig(
            windows_allowed_paths=(str(tmp_path) + os.sep,),
            windows_blocked_paths=(),
        )
        return WindowsExplorerServer(
            path_guard=WindowsPathGuard(config),
            safety=MagicMock(spec=WindowsSafetyChecker),
            audit=MagicMock(spec=WindowsAuditLog),
        )

    def test_list_tools(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        names = {t.name for t in srv.list_tools()}
        assert names == {
            "open_folder_in_explorer",
            "navigate_explorer_to_path",
            "open_file_with_default_app",
            "select_files_in_explorer",
        }

    def test_server_name(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        for t in srv.list_tools():
            assert t.server_name == "windows-explorer"

    async def test_non_windows_error(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_explorer._WINDOWS_ONLY", False):
            result = await srv.call_tool("open_folder_in_explorer", {"path": str(tmp_path)})
        assert "Windows" in result.content

    async def test_path_guard_rejection(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        outside = str(tmp_path.parent / "outside")
        with patch("anythink.mcp.builtin.windows_explorer._WINDOWS_ONLY", True):
            result = await srv.call_tool("open_folder_in_explorer", {"path": outside})
        assert result.is_error
        assert "access denied" in result.content.lower() or "not within" in result.content.lower()

    async def test_open_folder_calls_explorer_exe(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        folder = tmp_path / "test_folder"
        folder.mkdir()
        mock_popen = MagicMock()
        with (
            patch("anythink.mcp.builtin.windows_explorer._WINDOWS_ONLY", True),
            patch("anythink.mcp.builtin.windows_explorer.subprocess.Popen", mock_popen),
        ):
            result = await srv.call_tool("open_folder_in_explorer", {"path": str(folder)})
        assert not result.is_error
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "explorer.exe" in args

    async def test_open_file_with_default_app(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        f = tmp_path / "test.txt"
        f.write_text("hello")
        mock_startfile = MagicMock()
        with (
            patch("anythink.mcp.builtin.windows_explorer._WINDOWS_ONLY", True),
            patch("anythink.mcp.builtin.windows_explorer.os.startfile", mock_startfile),
        ):
            result = await srv.call_tool("open_file_with_default_app", {"path": str(f)})
        assert not result.is_error
        mock_startfile.assert_called_once_with(str(f))

    async def test_open_file_not_found(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        missing = str(tmp_path / "missing.txt")
        with patch("anythink.mcp.builtin.windows_explorer._WINDOWS_ONLY", True):
            result = await srv.call_tool("open_file_with_default_app", {"path": missing})
        assert "not found" in result.content.lower() or result.is_error

    async def test_unknown_tool(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        result = await srv.call_tool("bogus", {})
        assert result.is_error
