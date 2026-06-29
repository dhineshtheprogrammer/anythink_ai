"""Tests for WindowsScreenshotServer."""

from __future__ import annotations

import io
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from anythink.config.schema import AppConfig
from anythink.mcp.builtin.windows_screenshot import WindowsScreenshotServer
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.paths import WindowsPathGuard
from anythink.mcp.windows.safety import WindowsSafetyChecker


class TestWindowsScreenshotServer:
    def _make_server(
        self,
        tmp_path: Path,
        vision_capable: bool = False,
        gui_mode: bool = False,
    ) -> WindowsScreenshotServer:
        config = AppConfig(
            windows_allowed_paths=(str(tmp_path) + os.sep,),
            windows_blocked_paths=(),
        )
        return WindowsScreenshotServer(
            safety=MagicMock(spec=WindowsSafetyChecker),
            audit=MagicMock(spec=WindowsAuditLog),
            vision_capable=vision_capable,
            gui_mode=gui_mode,
            max_px=1920,
            path_guard=WindowsPathGuard(config),
        )

    def test_list_tools(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        names = {t.name for t in srv.list_tools()}
        assert names == {"take_screenshot", "take_window_screenshot", "save_screenshot"}
        for t in srv.list_tools():
            assert t.server_name == "windows-screenshot"

    async def test_non_windows_error(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        with patch("anythink.mcp.builtin.windows_screenshot._WINDOWS_ONLY", False):
            result = await srv.call_tool("take_screenshot", {})
        assert "Windows" in result.content

    async def test_take_screenshot_requires_gui_mode(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path, gui_mode=False)
        with patch("anythink.mcp.builtin.windows_screenshot._WINDOWS_ONLY", True):
            result = await srv.call_tool("take_screenshot", {})
        assert "gui" in result.content.lower() or "GUI" in result.content

    async def test_take_window_screenshot_requires_gui_mode(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path, gui_mode=False)
        with patch("anythink.mcp.builtin.windows_screenshot._WINDOWS_ONLY", True):
            result = await srv.call_tool("take_window_screenshot", {"title": "Test"})
        assert "gui" in result.content.lower() or "GUI" in result.content

    async def test_save_screenshot_path_guard_rejection(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        outside = str(tmp_path.parent / "outside" / "screen.png")
        with patch("anythink.mcp.builtin.windows_screenshot._WINDOWS_ONLY", True):
            result = await srv.call_tool("save_screenshot", {"path": outside})
        assert "access denied" in result.content.lower() or "not within" in result.content.lower()

    async def test_take_screenshot_vision_path(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path, vision_capable=True, gui_mode=True)
        mock_img = MagicMock()
        mock_img.width = 800
        mock_img.height = 600
        mock_img.size = (800, 600)
        mock_img.save = MagicMock(side_effect=lambda buf, **kw: buf.write(b"FAKE_JPEG"))
        mock_grab = MagicMock(return_value=mock_img)
        with (
            patch("anythink.mcp.builtin.windows_screenshot._WINDOWS_ONLY", True),
            patch("anythink.mcp.builtin.windows_screenshot.io", io),
        ):
            pil_mock = MagicMock()
            pil_mock.ImageGrab.grab.return_value = mock_img
            with patch.dict("sys.modules", {"PIL": pil_mock, "PIL.ImageGrab": pil_mock.ImageGrab}):
                with patch.object(srv, "_grab_full", return_value=mock_img):
                    result = await srv.call_tool("take_screenshot", {})
        assert not result.is_error
        assert "[IMAGE_BASE64]" in result.content or "vision" in result.content.lower()

    async def test_take_screenshot_ocr_fallback(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path, vision_capable=False, gui_mode=True)
        mock_img = MagicMock()
        mock_img.width = 800
        mock_img.height = 600
        with patch.object(srv, "_grab_full", return_value=mock_img):
            mock_tess = MagicMock()
            mock_tess.image_to_string.return_value = "Extracted text"
            with patch.dict("sys.modules", {"pytesseract": mock_tess}):
                with patch("anythink.mcp.builtin.windows_screenshot._WINDOWS_ONLY", True):
                    result = await srv.call_tool("take_screenshot", {})
        assert not result.is_error
        assert "Extracted text" in result.content or "OCR" in result.content

    async def test_save_screenshot_success(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        dest = str(tmp_path / "capture.png")
        mock_img = MagicMock()
        mock_img.width = 1920
        mock_img.height = 1080
        with (
            patch("anythink.mcp.builtin.windows_screenshot._WINDOWS_ONLY", True),
            patch.object(srv, "_grab_full", return_value=mock_img),
        ):
            # mock save to actually write a file so stat() works
            def _fake_save(path: str, **kw: object) -> None:
                Path(path).write_bytes(b"PNG")
            mock_img.save.side_effect = _fake_save
            result = await srv.call_tool("save_screenshot", {"path": dest})
        assert not result.is_error
        assert "capture.png" in result.content

    async def test_unknown_tool(self, tmp_path: Path) -> None:
        srv = self._make_server(tmp_path)
        result = await srv.call_tool("capture_everything", {})
        assert result.is_error
