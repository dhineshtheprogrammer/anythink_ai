"""Windows Explorer MCP server — open folders and files in Windows File Explorer."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.paths import WindowsPathGuard
from anythink.mcp.windows.safety import WindowsSafetyChecker

_WINDOWS_ONLY = sys.platform == "win32"
_WIN_ERR = f"This tool requires Windows. Current platform: {sys.platform}"


class WindowsExplorerServer(BuiltinMCPServer):
    """Open and navigate Windows File Explorer; open files with their default applications."""

    name = "windows-explorer"
    description = (
        "Open and navigate Windows File Explorer; open files with their default applications."
    )

    def __init__(
        self,
        path_guard: WindowsPathGuard,
        safety: WindowsSafetyChecker,
        audit: WindowsAuditLog,
    ) -> None:
        self._path_guard = path_guard
        self._safety = safety
        self._audit = audit

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                "open_folder_in_explorer",
                "Open a folder in a new File Explorer window.",
                {"path": {"type": "string", "description": "Folder path to open"}},
                self.name,
            ),
            MCPTool(
                "navigate_explorer_to_path",
                "Open a File Explorer window navigated to a specific path.",
                {
                    "path": {"type": "string", "description": "Target path"},
                    "window_title": {"type": "string", "description": "Explorer window title to navigate (optional)"},
                },
                self.name,
            ),
            MCPTool(
                "open_file_with_default_app",
                "Open a file using its associated default application (like double-clicking).",
                {"path": {"type": "string", "description": "File path to open"}},
                self.name,
            ),
            MCPTool(
                "select_files_in_explorer",
                "Open File Explorer with specific files pre-selected.",
                {"paths": {"type": "array", "description": "List of file paths to select"}},
                self.name,
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        t0 = time.monotonic()
        tier = self._safety.get_tier(self.name, name, **arguments)
        # Validate paths before proceeding
        paths_to_check: list[str] = []
        if "path" in arguments:
            paths_to_check.append(str(arguments["path"]))
        if "paths" in arguments:
            paths_to_check.extend(str(p) for p in arguments.get("paths", []))

        for p in paths_to_check:
            err = self._path_guard.validate(p)
            if err:
                self._audit.log(
                    session_id="",
                    server=self.name,
                    tool=name,
                    tier=tier,
                    arguments=arguments,
                    confirmation_status="not_required",
                    outcome="blocked_by_path_guard",
                    duration_s=round(time.monotonic() - t0, 4),
                    error=err,
                )
                return MCPCallResult(
                    tool_name=name,
                    server_name=self.name,
                    content=err,
                    is_error=True,
                    duration_s=round(time.monotonic() - t0, 3),
                )

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
        if name == "open_folder_in_explorer":
            return self._open_folder(str(arguments.get("path", "")))
        if name == "navigate_explorer_to_path":
            return self._navigate_explorer(
                path=str(arguments.get("path", "")),
                window_title=arguments.get("window_title"),
            )
        if name == "open_file_with_default_app":
            return self._open_file(str(arguments.get("path", "")))
        if name == "select_files_in_explorer":
            return self._select_files(list(arguments.get("paths", [])))
        raise ValueError(f"Unknown tool '{name}'")

    def _open_folder(self, path: str) -> str:
        if not path:
            return "Provide a folder path."
        if not os.path.isdir(path):
            return f"Not a directory: {path}"
        subprocess.Popen(["explorer.exe", path])
        return f"File Explorer opened at '{path}'."

    def _navigate_explorer(self, path: str, window_title: Any) -> str:
        if not path:
            return "Provide a path."
        # Always open a new Explorer window at the target path
        subprocess.Popen(["explorer.exe", path])
        return f"File Explorer opened at '{path}'."

    def _open_file(self, path: str) -> str:
        if not path:
            return "Provide a file path."
        if not os.path.exists(path):
            return f"File not found: {path}"
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return f"File '{path}' opened with its default application."
        except OSError as e:
            return f"Failed to open '{path}': {e}"

    def _select_files(self, paths: list[str]) -> str:
        if not paths:
            return "Provide at least one file path."

        # Group by parent directory — open one Explorer per directory
        from collections import defaultdict
        dir_groups: dict[str, list[str]] = defaultdict(list)
        for p in paths:
            parent = os.path.dirname(os.path.abspath(p))
            dir_groups[parent].append(p)

        opened = []
        for parent, file_paths in dir_groups.items():
            # Try SHOpenFolderAndSelectItems via win32com
            try:
                import win32com.shell.shell as shell  # type: ignore[import]
                pidl = shell.SHParseDisplayName(parent, 0, None)[0]
                items = [shell.SHParseDisplayName(f, 0, None)[0] for f in file_paths]
                shell.SHOpenFolderAndSelectItems(pidl, items, 0)
                opened.append(f"Opened Explorer in '{parent}' with {len(items)} item(s) selected.")
            except (ImportError, Exception):
                # Fallback: open folder and select first file via /select,
                if file_paths:
                    subprocess.Popen(["explorer.exe", "/select,", file_paths[0]])
                    opened.append(f"Opened Explorer in '{parent}' (fallback — first file selected).")

        return "\n".join(opened) if opened else "No files to open."
