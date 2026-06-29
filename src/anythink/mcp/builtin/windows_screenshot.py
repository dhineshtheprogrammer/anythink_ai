"""Windows Screenshot MCP server — capture screen and inject into conversation."""

from __future__ import annotations

import base64
import io
import sys
import time
from pathlib import Path
from typing import Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.paths import WindowsPathGuard
from anythink.mcp.windows.safety import WindowsSafetyChecker

_WINDOWS_ONLY = sys.platform == "win32"
_WIN_ERR = f"This tool requires Windows. Current platform: {sys.platform}"
_GUI_ERR = (
    "This tool requires GUI mode to inject screenshots into the conversation. "
    "Run '/mcp windows mode gui' to enable it, or use 'save_screenshot' to save to a file."
)


class WindowsScreenshotServer(BuiltinMCPServer):
    """Capture screenshots of the full screen or a specific window."""

    name = "windows-screenshot"
    description = (
        "Capture screenshots of the full screen or a specific window and use them "
        "as conversation context."
    )

    def __init__(
        self,
        safety: WindowsSafetyChecker,
        audit: WindowsAuditLog,
        vision_capable: bool = False,
        gui_mode: bool = False,
        max_px: int = 1920,
        path_guard: WindowsPathGuard | None = None,
    ) -> None:
        self._safety = safety
        self._audit = audit
        self._vision_capable = vision_capable
        self._gui_mode = gui_mode
        self._max_px = max_px
        self._path_guard = path_guard

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                "take_screenshot",
                "Capture the full screen and use it as conversation context. Requires GUI mode.",
                {},
                self.name,
            ),
            MCPTool(
                "take_window_screenshot",
                "Capture a specific window by title and use it as conversation context. Requires GUI mode.",
                {"title": {"type": "string", "description": "Window title (partial match)"}},
                self.name,
            ),
            MCPTool(
                "save_screenshot",
                "Capture the screen and save it to a file path.",
                {"path": {"type": "string", "description": "Destination file path (.png or .jpg)"}},
                self.name,
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        t0 = time.monotonic()
        tier = self._safety.get_tier(self.name, name, **arguments)
        try:
            content = self._dispatch(name, arguments)
            outcome = "success"
            error = None
        except Exception as exc:
            content = str(exc)
            outcome = "error"
            error = str(exc)
        duration = round(time.monotonic() - t0, 3)
        self._audit.log(
            session_id="",
            server=self.name,
            tool=name,
            tier=tier,
            arguments=arguments,
            confirmation_status="auto",
            outcome=outcome,
            duration_s=duration,
            error=error,
        )
        return MCPCallResult(
            tool_name=name,
            server_name=self.name,
            content=content,
            is_error=error is not None,
            duration_s=duration,
        )

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if not _WINDOWS_ONLY:
            return _WIN_ERR
        if name == "take_screenshot":
            if not self._gui_mode:
                return _GUI_ERR
            return self._take_full_screenshot()
        if name == "take_window_screenshot":
            if not self._gui_mode:
                return _GUI_ERR
            return self._take_window_screenshot(str(arguments.get("title", "")))
        if name == "save_screenshot":
            path = str(arguments.get("path", ""))
            if self._path_guard:
                err = self._path_guard.validate(path)
                if err:
                    return err
            return self._save_screenshot(path)
        raise ValueError(f"Unknown tool '{name}'")

    def _grab_full(self) -> Any:
        try:
            from PIL import ImageGrab  # type: ignore[import]
        except ImportError:
            raise ImportError("Pillow not installed. Run: pip install anythink[windows]")
        return ImageGrab.grab()

    def _scale_if_needed(self, img: Any) -> Any:
        if img.width > self._max_px:
            try:
                from PIL import Image  # type: ignore[import]
                ratio = self._max_px / img.width
                new_h = int(img.height * ratio)
                img = img.resize((self._max_px, new_h), Image.LANCZOS)
            except Exception:
                pass
        return img

    def _encode_image(self, img: Any) -> str:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        orig_w, orig_h = img.size
        kb = len(buf.getvalue()) // 1024
        return (
            f"[IMAGE_BASE64]data:image/jpeg;base64,{b64}\n"
            f"Screenshot captured: {orig_w}×{orig_h} px  ({kb} KB JPEG)  "
            f"Mode: injected as conversation context  Vision: ✓"
        )

    def _ocr_image(self, img: Any) -> str:
        try:
            import pytesseract  # type: ignore[import]
            text = pytesseract.image_to_string(img)
            return f"Screenshot captured (OCR text extraction — model is not vision-capable):\n\n{text}"
        except ImportError:
            return (
                "Screenshot captured but active model does not support vision input. "
                "Install pytesseract for OCR fallback, or switch to a vision-capable model."
            )

    def _take_full_screenshot(self) -> str:
        img = self._grab_full()
        img = self._scale_if_needed(img)
        if self._vision_capable:
            return self._encode_image(img)
        return self._ocr_image(img)

    def _take_window_screenshot(self, title: str) -> str:
        if not title:
            return "Provide a window title."
        try:
            import pygetwindow as gw  # type: ignore[import]
        except ImportError:
            return "pygetwindow not installed. Run: pip install anythink[windows]"

        # Find the window
        matches = gw.getWindowsWithTitle(title)
        if not matches:
            title_lower = title.lower()
            matches = [w for w in gw.getAllWindows() if title_lower in (w.title or "").lower()]
        if not matches:
            return f"No window matching '{title}' found."

        win = matches[0]
        try:
            bbox = (win.left, win.top, win.right, win.bottom)
        except Exception as e:
            return f"Could not get window bounds: {e}"

        try:
            from PIL import ImageGrab  # type: ignore[import]
        except ImportError:
            return "Pillow not installed. Run: pip install anythink[windows]"

        img = ImageGrab.grab(bbox=bbox)
        img = self._scale_if_needed(img)
        if self._vision_capable:
            return self._encode_image(img)
        return self._ocr_image(img)

    def _save_screenshot(self, path: str) -> str:
        if not path:
            return "Provide a destination file path."
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            img = self._grab_full()
            img = self._scale_if_needed(img)
            fmt = "JPEG" if str(path).lower().endswith((".jpg", ".jpeg")) else "PNG"
            img.save(str(dest), format=fmt)
            kb = dest.stat().st_size // 1024
            return f"Screenshot saved to '{dest}' ({img.width}×{img.height} px, {kb} KB)."
        except Exception as e:
            return f"Failed to save screenshot: {e}"
