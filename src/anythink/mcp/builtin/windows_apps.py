"""Windows Apps MCP server — discover and launch installed applications."""

from __future__ import annotations

import difflib
import os
import subprocess
import sys
import time
from typing import Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.safety import WindowsSafetyChecker

_WINDOWS_ONLY = sys.platform == "win32"
_WIN_ERR = f"This tool requires Windows. Current platform: {sys.platform}"


class WindowsAppsServer(BuiltinMCPServer):
    """Launch installed Windows applications by name."""

    name = "windows-apps"
    description = "Launch installed Windows applications by name."

    def __init__(
        self,
        safety: WindowsSafetyChecker,
        audit: WindowsAuditLog,
        blocked_apps: tuple[str, ...] = ("regedit.exe", "cmd.exe", "powershell.exe", "mmc.exe"),
        cache_ttl_minutes: int = 60,
    ) -> None:
        self._safety = safety
        self._audit = audit
        self._blocked_apps = frozenset(a.lower() for a in blocked_apps)
        self._cache_ttl = cache_ttl_minutes * 60
        self._cache: list[dict[str, str]] | None = None
        self._cache_time: float = 0.0

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                "list_installed_apps",
                "List all installed applications discoverable on this system.",
                {},
                self.name,
            ),
            MCPTool(
                "launch_app",
                "Launch an installed application by name (fuzzy match).",
                {
                    "name": {"type": "string", "description": "Application name to launch"},
                    "args": {"type": "array", "description": "Additional command-line arguments", "default": []},
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
        if name == "list_installed_apps":
            return self._list_installed_apps()
        if name == "launch_app":
            return self._launch_app(
                name=str(arguments.get("name", "")),
                args=list(arguments.get("args", [])),
            )
        raise ValueError(f"Unknown tool '{name}'")

    def _get_cache(self) -> list[dict[str, str]]:
        if self._cache is not None and (time.monotonic() - self._cache_time) < self._cache_ttl:
            return self._cache
        apps = self._discover_apps()
        self._cache = apps
        self._cache_time = time.monotonic()
        return apps

    def _discover_apps(self) -> list[dict[str, str]]:
        seen: set[str] = set()
        apps: list[dict[str, str]] = []

        def _add(name: str, exe: str) -> None:
            key = name.lower()
            if key not in seen:
                seen.add(key)
                apps.append({"name": name, "exe": exe})

        # 1. Registry — HKLM and HKCU Uninstall keys
        try:
            import winreg  # type: ignore[import]
            for hive, path in [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            ]:
                try:
                    key = winreg.OpenKey(hive, path)
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            subkey = winreg.OpenKey(key, subkey_name)
                            try:
                                display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                                try:
                                    install_loc, _ = winreg.QueryValueEx(subkey, "InstallLocation")
                                except FileNotFoundError:
                                    install_loc = ""
                                if display_name:
                                    _add(str(display_name), str(install_loc))
                            except FileNotFoundError:
                                pass
                            winreg.CloseKey(subkey)
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except Exception:
                    pass
        except ImportError:
            pass

        # 2. PATH executables
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        for directory in path_dirs:
            if not directory or not os.path.isdir(directory):
                continue
            try:
                for entry in os.scandir(directory):
                    if entry.is_file() and entry.name.lower().endswith(".exe"):
                        base = os.path.splitext(entry.name)[0]
                        _add(base, entry.path)
            except PermissionError:
                pass

        apps.sort(key=lambda a: a["name"].lower())
        return apps

    def _list_installed_apps(self) -> str:
        apps = self._get_cache()
        lines = [
            f"Installed Applications ({len(apps)} found)",
            "─" * 70,
            f"{'Name':<40} Executable / Location",
            "─" * 70,
        ]
        for app in apps[:200]:
            lines.append(f"{app['name'][:39]:<40} {app['exe'][:50]}")
        if len(apps) > 200:
            lines.append(f"... and {len(apps) - 200} more (use 'apps refresh' to rebuild list)")
        return "\n".join(lines)

    def _launch_app(self, name: str, args: list[str]) -> str:
        if not name:
            return "Provide an application name."
        apps = self._get_cache()
        app_names = [a["name"] for a in apps]

        # Fuzzy match
        close = difflib.get_close_matches(name, app_names, n=3, cutoff=0.6)
        if not close:
            # Try case-insensitive substring
            close = [a["name"] for a in apps if name.lower() in a["name"].lower()][:3]
        if not close:
            return f"No application matching '{name}' found. Use 'list_installed_apps' to browse."

        # Use best match
        matched_name = close[0]
        matched_app = next((a for a in apps if a["name"] == matched_name), None)
        if matched_app is None:
            return f"Could not resolve application '{matched_name}'."

        exe = matched_app["exe"]
        exe_basename = os.path.basename(exe).lower() if exe else matched_name.lower()

        if exe_basename in self._blocked_apps or matched_name.lower() in self._blocked_apps:
            return (
                f"Cannot launch '{matched_name}': it is on the blocked applications list. "
                "Use '/mcp windows apps unblock <name>' to remove it."
            )

        if not exe or not os.path.isfile(exe):
            # Try to find it via PATH
            import shutil
            found = shutil.which(matched_name) or shutil.which(exe_basename)
            if found:
                exe = found
            else:
                return (
                    f"Found '{matched_name}' in registry but cannot locate its executable. "
                    "Try launching it manually."
                )

        try:
            cmd = [exe] + [str(a) for a in args]
            proc = subprocess.Popen(cmd)
            result = f"Launched '{matched_name}' (PID {proc.pid})."
            if len(close) > 1:
                result += f" Note: other matches were: {', '.join(close[1:])}"
            return result
        except Exception as e:
            return f"Failed to launch '{matched_name}': {e}"

    def invalidate_cache(self) -> None:
        self._cache = None
        self._cache_time = 0.0
