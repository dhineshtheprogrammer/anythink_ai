"""Tests for WindowsFilesystemServer."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from anythink.config.schema import AppConfig
from anythink.mcp.builtin.windows_filesystem import (
    WindowsFilesystemServer,
    _MAX_WRITE_BYTES,
    _TOOL_NAMES,
)
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.paths import WindowsPathGuard
from anythink.mcp.windows.safety import WindowsSafetyChecker


class TestWindowsFilesystemServer:
    def _make_server(self, tmp_path: Path) -> WindowsFilesystemServer:
        config = AppConfig(
            windows_allowed_paths=(str(tmp_path) + os.sep,),
            windows_blocked_paths=(),
        )
        return WindowsFilesystemServer(
            path_guard=WindowsPathGuard(config),
            safety=WindowsSafetyChecker(),
            audit=MagicMock(spec=WindowsAuditLog),
        )

    def test_tool_names_constant(self) -> None:
        assert len(_TOOL_NAMES) == 13

    def test_list_tools_matches_constant(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        tool_names = {t.name for t in srv.list_tools()}
        assert tool_names == _TOOL_NAMES

    def test_server_name_on_tools(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        for t in srv.list_tools():
            assert t.server_name == "windows-filesystem"

    async def test_non_windows_returns_message(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", False):
            result = await srv.call_tool("list_dir", {"path": str(tmp_path)})
        assert "Windows" in result.content

    async def test_path_guard_rejects_outside_allowed(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        outside = str(tmp_path.parent / "secret.txt")
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", True):
            result = await srv.call_tool("read_file", {"path": outside})
        assert result.is_error
        assert "access denied" in result.content.lower()

    async def test_list_dir_success(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("hello")
        (tmp_path / "subdir").mkdir()
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", True):
            result = await srv.call_tool("list_dir", {"path": str(tmp_path)})
        assert not result.is_error
        assert "file.txt" in result.content
        assert "subdir" in result.content

    async def test_read_file_success(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", True):
            result = await srv.call_tool("read_file", {"path": str(f)})
        assert not result.is_error
        assert "hello world" in result.content

    async def test_write_file_size_cap(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        big_content = "X" * (_MAX_WRITE_BYTES + 1)
        dest = str(tmp_path / "big.txt")
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", True):
            result = await srv.call_tool("write_file", {"path": dest, "content": big_content})
        assert "too large" in result.content.lower() or "maximum" in result.content.lower()

    async def test_write_file_new_creates_file(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        dest = str(tmp_path / "new.txt")
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", True):
            result = await srv.call_tool(
                "write_file",
                {"path": dest, "content": "content", "overwrite": False},
            )
        assert not result.is_error
        assert Path(dest).read_text() == "content"

    async def test_write_file_refuses_overwrite_without_flag(self, tmp_path: Path) -> None:
        f = tmp_path / "existing.txt"
        f.write_text("original")
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", True):
            result = await srv.call_tool(
                "write_file",
                {"path": str(f), "content": "new", "overwrite": False},
            )
        assert "already exists" in result.content.lower() or "overwrite" in result.content.lower()
        assert f.read_text() == "original"

    async def test_delete_file_success(self, tmp_path: Path) -> None:
        f = tmp_path / "del.txt"
        f.write_text("bye")
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", True):
            result = await srv.call_tool("delete_file", {"path": str(f)})
        assert not result.is_error
        assert not f.exists()

    async def test_delete_folder_empty_tier3(self, tmp_path: Path) -> None:
        d = tmp_path / "empty_dir"
        d.mkdir()
        safety = WindowsSafetyChecker()
        tier = safety.get_tier("windows-filesystem", "delete_folder", recursive=False)
        assert tier == 3

    async def test_delete_folder_recursive_tier4(self) -> None:
        safety = WindowsSafetyChecker()
        tier = safety.get_tier("windows-filesystem", "delete_folder", recursive=True)
        assert tier == 4

    async def test_delete_nonempty_folder_without_recursive(self, tmp_path: Path) -> None:
        d = tmp_path / "nonempty"
        d.mkdir()
        (d / "file.txt").write_text("x")
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", True):
            result = await srv.call_tool("delete_folder", {"path": str(d), "recursive": False})
        # Should refuse and suggest recursive=True
        assert "recursive" in result.content.lower() or not result.is_error
        assert d.exists()

    async def test_get_file_metadata(self, tmp_path: Path) -> None:
        f = tmp_path / "meta.txt"
        f.write_text("hello")
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", True):
            result = await srv.call_tool("get_file_metadata", {"path": str(f)})
        assert not result.is_error
        assert "meta.txt" in result.content

    async def test_search_files_by_name(self, tmp_path: Path) -> None:
        (tmp_path / "report.txt").write_text("a")
        (tmp_path / "notes.md").write_text("b")
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", True):
            result = await srv.call_tool(
                "search_files_by_name",
                {"root_path": str(tmp_path), "pattern": "*.txt"},
            )
        assert not result.is_error
        assert "report.txt" in result.content
        assert "notes.md" not in result.content

    async def test_search_files_by_content(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hello secret world")
        (tmp_path / "b.txt").write_text("nothing special here")
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_filesystem._WINDOWS_ONLY", True):
            result = await srv.call_tool(
                "search_files_by_content",
                {"root_path": str(tmp_path), "query": "secret"},
            )
        assert not result.is_error
        assert "a.txt" in result.content
        assert "b.txt" not in result.content

    async def test_unknown_tool(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        result = await srv.call_tool("annihilate", {})
        assert result.is_error
