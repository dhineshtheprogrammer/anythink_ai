"""Windows Window MCP server — list, focus, resize, and interact with open windows."""

from __future__ import annotations

import sys
import time
from typing import Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.safety import WindowsSafetyChecker

_WINDOWS_ONLY = sys.platform == "win32"
_WIN_ERR = f"This tool requires Windows. Current platform: {sys.platform}"
_GUI_ERR = (
    "This tool requires GUI mode. "
    "Run '/mcp windows mode gui' to enable it."
)


class WindowsWindowServer(BuiltinMCPServer):
    """List, focus, resize, and interact with open Windows application windows."""

    name = "windows-window"
    description = (
        "List, focus, resize, and interact with open Windows application windows."
    )

    def __init__(
        self,
        safety: WindowsSafetyChecker,
        audit: WindowsAuditLog,
        gui_mode: bool = False,
    ) -> None:
        self._safety = safety
        self._audit = audit
        self._gui_mode = gui_mode

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                "list_open_windows",
                "List all currently visible application windows with titles and states.",
                {},
                self.name,
            ),
            MCPTool(
                "bring_to_foreground",
                "Bring a specific window to the foreground and give it focus.",
                {"title": {"type": "string", "description": "Window title (partial match)"}},
                self.name,
            ),
            MCPTool(
                "minimize_window",
                "Minimize a window to the taskbar.",
                {"title": {"type": "string", "description": "Window title (partial match)"}},
                self.name,
            ),
            MCPTool(
                "maximize_window",
                "Maximize a window to fill the screen.",
                {"title": {"type": "string", "description": "Window title (partial match)"}},
                self.name,
            ),
            MCPTool(
                "restore_window",
                "Restore a minimized or maximized window to its normal size.",
                {"title": {"type": "string", "description": "Window title (partial match)"}},
                self.name,
            ),
            MCPTool(
                "close_window",
                "Close a window (sends WM_CLOSE — the application may prompt to save).",
                {"title": {"type": "string", "description": "Window title (partial match)"}},
                self.name,
            ),
            MCPTool(
                "send_text_to_window",
                "Type text into the currently focused control of a window. Requires GUI mode.",
                {
                    "title": {"type": "string", "description": "Window title (partial match)"},
                    "text": {"type": "string", "description": "Text to type"},
                    "press_enter": {"type": "boolean", "description": "Press Enter after text", "default": False},
                },
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
            confirmation_status="not_required" if tier == 1 else "auto",
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
        title = str(arguments.get("title", ""))
        if name == "list_open_windows":
            return self._list_open_windows()
        if name == "bring_to_foreground":
            return self._window_action(title, "activate")
        if name == "minimize_window":
            return self._window_action(title, "minimize")
        if name == "maximize_window":
            return self._window_action(title, "maximize")
        if name == "restore_window":
            return self._window_action(title, "restore")
        if name == "close_window":
            return self._close_window(title)
        if name == "send_text_to_window":
            if not self._gui_mode:
                return _GUI_ERR
            return self._send_text_to_window(
                title=title,
                text=str(arguments.get("text", "")),
                press_enter=bool(arguments.get("press_enter", False)),
            )
        raise ValueError(f"Unknown tool '{name}'")

    def _find_window(self, title: str) -> Any:
        try:
            import pygetwindow as gw  # type: ignore[import]
        except ImportError:
            raise ImportError("pygetwindow not installed. Run: pip install anythink[windows]")

        # Exact match first
        matches = gw.getWindowsWithTitle(title)
        if matches:
            return matches[0]

        # Fuzzy: substring match on all windows
        title_lower = title.lower()
        all_windows = gw.getAllWindows()
        for w in all_windows:
            if hasattr(w, "title") and title_lower in (w.title or "").lower():
                return w

        raise ValueError(f"No window matching '{title}' found.")

    def _list_open_windows(self) -> str:
        try:
            import pygetwindow as gw  # type: ignore[import]
        except ImportError:
            return "pygetwindow not installed. Run: pip install anythink[windows]"

        windows = [w for w in gw.getAllWindows() if hasattr(w, "title") and w.title]
        lines = [
            f"Open Windows ({len(windows)} windows)",
            "─" * 60,
            f"  {'Title':<45} State",
            "─" * 60,
        ]
        for w in windows:
            try:
                state = "Minimized" if w.isMinimized else ("Maximized" if w.isMaximized else "Normal")
            except Exception:
                state = "Unknown"
            lines.append(f"  {(w.title or '')[:44]:<45} {state}")
        return "\n".join(lines)

    def _window_action(self, title: str, action: str) -> str:
        if not title:
            return "Provide a window title."
        try:
            win = self._find_window(title)
        except (ValueError, ImportError) as e:
            return str(e)
        try:
            if action == "activate":
                win.activate()
                return f"Window '{win.title}' brought to foreground."
            elif action == "minimize":
                win.minimize()
                return f"Window '{win.title}' minimized."
            elif action == "maximize":
                win.maximize()
                return f"Window '{win.title}' maximized."
            elif action == "restore":
                win.restore()
                return f"Window '{win.title}' restored."
        except Exception as e:
            return f"Failed to {action} window: {e}"
        return "Unknown action."

    def _close_window(self, title: str) -> str:
        if not title:
            return "Provide a window title."
        try:
            win = self._find_window(title)
        except (ValueError, ImportError) as e:
            return str(e)
        try:
            import win32api  # type: ignore[import]
            import win32con  # type: ignore[import]
            hwnd = win._hWnd  # type: ignore[attr-defined]
            win32api.SendMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return f"WM_CLOSE sent to window '{win.title}'. The application may prompt to save."
        except ImportError:
            # Fallback: pygetwindow close
            try:
                win.close()
                return f"Window '{win.title}' closed."
            except Exception as e:
                return f"Failed to close window: {e}"
        except Exception as e:
            return f"Failed to close window: {e}"

    def _send_text_to_window(self, title: str, text: str, press_enter: bool) -> str:
        if not title:
            return "Provide a window title."
        try:
            win = self._find_window(title)
        except (ValueError, ImportError) as e:
            return str(e)
        try:
            win.activate()
        except Exception:
            pass
        try:
            import pyautogui  # type: ignore[import]
        except ImportError:
            return "pyautogui not installed. Run: pip install anythink[windows]"
        pyautogui.typewrite(text, interval=0.05)
        if press_enter:
            pyautogui.press("enter")
        return f"Text typed into window '{win.title}'."
