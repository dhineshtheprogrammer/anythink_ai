"""Windows Settings MCP server — read and change volume, brightness, power plan, timezone."""

from __future__ import annotations

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


class WindowsSettingsServer(BuiltinMCPServer):
    """Read and change Windows system settings: volume, brightness, power plan, timezone."""

    name = "windows-settings"
    description = (
        "Read and change Windows system settings: volume, display brightness, "
        "power plan, and time zone."
    )

    def __init__(self, safety: WindowsSafetyChecker, audit: WindowsAuditLog) -> None:
        self._safety = safety
        self._audit = audit

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool("get_volume", "Get current system volume level (0–100) and mute state.", {}, self.name),
            MCPTool(
                "set_volume",
                "Set system volume to a specific level (0–100).",
                {"level": {"type": "integer", "description": "Volume level 0–100"}},
                self.name,
            ),
            MCPTool(
                "mute_audio",
                "Mute or unmute system audio.",
                {"mute": {"type": "boolean", "description": "True to mute, False to unmute"}},
                self.name,
            ),
            MCPTool("get_brightness", "Get current display brightness (0–100).", {}, self.name),
            MCPTool(
                "set_brightness",
                "Set display brightness to a specific level (0–100).",
                {"level": {"type": "integer", "description": "Brightness level 0–100"}},
                self.name,
            ),
            MCPTool("get_power_plan", "Get current active power plan name.", {}, self.name),
            MCPTool("list_power_plans", "List all available power plans.", {}, self.name),
            MCPTool(
                "set_power_plan",
                "Switch to a specified power plan by name.",
                {"name": {"type": "string", "description": "Power plan name (e.g. 'Balanced', 'High performance')"}},
                self.name,
            ),
            MCPTool("get_timezone", "Get current system time zone.", {}, self.name),
            MCPTool(
                "set_timezone",
                "Change system time zone. Requires administrator privileges.",
                {"timezone": {"type": "string", "description": "Windows time zone name (e.g. 'Pacific Standard Time')"}},
                self.name,
            ),
            MCPTool("get_display_info", "Get display resolution, refresh rate, and scaling for all monitors.", {}, self.name),
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
        if name == "get_volume":
            return self._get_volume()
        if name == "set_volume":
            return self._set_volume(int(arguments.get("level", 50)))
        if name == "mute_audio":
            return self._mute_audio(bool(arguments.get("mute", True)))
        if name == "get_brightness":
            return self._get_brightness()
        if name == "set_brightness":
            return self._set_brightness(int(arguments.get("level", 50)))
        if name == "get_power_plan":
            return self._get_power_plan()
        if name == "list_power_plans":
            return self._list_power_plans()
        if name == "set_power_plan":
            return self._set_power_plan(str(arguments.get("name", "")))
        if name == "get_timezone":
            return self._get_timezone()
        if name == "set_timezone":
            return self._set_timezone(str(arguments.get("timezone", "")))
        if name == "get_display_info":
            return self._get_display_info()
        raise ValueError(f"Unknown tool '{name}'")

    # ------------------------------------------------------------------ volume

    def _get_volume(self) -> str:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Math]::Round((Get-AudioDevice -Playback).Volume)"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip().isdigit():
                return f"System volume: {result.stdout.strip()}%"
        except Exception:
            pass
        # Fallback: use pycaw/comtypes via PowerShell script
        try:
            ps_script = (
                "Add-Type -TypeDefinition @'\n"
                "using System.Runtime.InteropServices;\n"
                "[Guid(\"5CDF2C82-841E-4546-9722-0CF74078229A\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
                "interface IAudioEndpointVolume { void a(); void b(); void c(); void d();\n"
                "  void SetMasterVolumeLevelScalar(float, System.Guid); void f();\n"
                "  float GetMasterVolumeLevelScalar(); }\n"
                "'@\n"
                "$obj = [Activator]::CreateInstance([Type]::GetTypeFromCLSID([Guid]'BCDE0395-E52F-467C-8E3D-C4579291692E'))\n"
                "Write-Output ([int]($obj.GetMasterVolumeLevelScalar() * 100))"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=8,
            )
            if r.returncode == 0:
                return f"System volume: {r.stdout.strip()}%"
        except Exception:
            pass
        return "Volume information unavailable (requires AudioDevice module or elevated PowerShell)."

    def _set_volume(self, level: int) -> str:
        level = max(0, min(100, level))
        try:
            ps = (
                f"$obj = [Activator]::CreateInstance([Type]::GetTypeFromCLSID([Guid]'BCDE0395-E52F-467C-8E3D-C4579291692E'));"
                f"$obj.SetMasterVolumeLevelScalar({level / 100:.4f}, [Guid]::Empty)"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=8,
            )
            if result.returncode == 0:
                return f"System volume set to {level}%."
            return f"Failed to set volume: {result.stderr.strip()}"
        except Exception as e:
            return f"Error setting volume: {e}"

    def _mute_audio(self, mute: bool) -> str:
        action = "Mute" if mute else "Unmute"
        try:
            ps = (
                "$obj = [Activator]::CreateInstance([Type]::GetTypeFromCLSID([Guid]'BCDE0395-E52F-467C-8E3D-C4579291692E'));"
                f"$obj.SetMute({'$true' if mute else '$false'}, [Guid]::Empty)"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=8,
            )
            if result.returncode == 0:
                return f"Audio {'muted' if mute else 'unmuted'}."
            return f"Failed to {action.lower()} audio: {result.stderr.strip()}"
        except Exception as e:
            return f"Error: {e}"

    # -------------------------------------------------------------- brightness

    def _get_brightness(self) -> str:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"],
                capture_output=True, text=True, timeout=5,
            )
            val = result.stdout.strip()
            if val and val.isdigit():
                return f"Display brightness: {val}%"
        except Exception:
            pass
        return "Brightness information unavailable (built-in displays / WMI-capable monitors only)."

    def _set_brightness(self, level: int) -> str:
        level = max(0, min(100, level))
        try:
            ps = (
                f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                f".WmiSetBrightness(1,{level})"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=8,
            )
            if result.returncode == 0:
                return f"Display brightness set to {level}%."
            return f"Failed to set brightness: {result.stderr.strip()}"
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------------------- power plans

    def _list_power_plans(self) -> str:
        try:
            result = subprocess.run(
                ["powercfg", "/list"], capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() or "No power plans found."
        except FileNotFoundError:
            return "powercfg not available."

    def _get_power_plan(self) -> str:
        try:
            result = subprocess.run(
                ["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() or "Unknown."
        except FileNotFoundError:
            return "powercfg not available."

    def _set_power_plan(self, plan_name: str) -> str:
        if not plan_name:
            return "Provide a power plan name."
        # Fetch plans and find GUID matching name
        try:
            result = subprocess.run(
                ["powercfg", "/list"], capture_output=True, text=True, timeout=5
            )
        except FileNotFoundError:
            return "powercfg not available."

        for line in result.stdout.splitlines():
            if plan_name.lower() in line.lower():
                # Extract GUID — format: Power Scheme GUID: <GUID>  (<name>)
                parts = line.split()
                for part in parts:
                    if len(part) == 36 and part.count("-") == 4:
                        guid = part
                        r = subprocess.run(
                            ["powercfg", "/setactive", guid],
                            capture_output=True, text=True, timeout=5,
                        )
                        if r.returncode == 0:
                            return f"Power plan switched to '{plan_name}' (GUID {guid})."
                        return f"Failed: {r.stderr.strip()}"
        return f"No power plan matching '{plan_name}' found. Use 'list_power_plans' to see available plans."

    # --------------------------------------------------------------- timezone

    def _get_timezone(self) -> str:
        try:
            result = subprocess.run(
                ["tzutil", "/g"], capture_output=True, text=True, timeout=5
            )
            return f"Current time zone: {result.stdout.strip()}"
        except FileNotFoundError:
            return "tzutil not available."

    def _set_timezone(self, timezone: str) -> str:
        if not timezone:
            return "Provide a Windows time zone name (e.g. 'Pacific Standard Time')."
        try:
            result = subprocess.run(
                ["tzutil", "/s", timezone], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return f"Time zone set to '{timezone}'."
            err = result.stderr.strip() or "Invalid time zone name or insufficient privileges."
            return f"Failed to set time zone: {err}"
        except FileNotFoundError:
            return "tzutil not available."
        except PermissionError:
            return "Setting time zone requires administrator privileges. Run Anythink as administrator."

    # ------------------------------------------------------------ display info

    def _get_display_info(self) -> str:
        try:
            ps = (
                "Get-WmiObject Win32_VideoController | "
                "Select-Object Name,CurrentHorizontalResolution,CurrentVerticalResolution,"
                "CurrentRefreshRate | Format-List"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=8,
            )
            return result.stdout.strip() or "Display information unavailable."
        except Exception as e:
            return f"Error: {e}"
