"""Windows System Information MCP server — all tools are Tier 1 read-only."""

from __future__ import annotations

import sys
import time
from typing import Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool
from anythink.mcp.windows.audit import WindowsAuditLog

_WINDOWS_ONLY = sys.platform == "win32"
_WIN_ERR = f"This tool requires Windows. Current platform: {sys.platform}"
_IMPORT_ERR = "psutil not installed. Run: pip install anythink[windows]"


class WindowsSystemServer(BuiltinMCPServer):
    """Read hardware and OS information: CPU, RAM, disk, network, battery, and software."""

    name = "windows-system"
    description = (
        "Read system hardware and OS information: CPU, RAM, disk, network, battery, "
        "and installed software."
    )

    def __init__(self, audit: WindowsAuditLog) -> None:
        self._audit = audit

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool("get_cpu_info", "CPU model, core count, and current usage per core.", {}, self.name),
            MCPTool("get_ram_info", "Total, used, and free RAM with usage percentage.", {}, self.name),
            MCPTool("get_disk_info", "All drives with total, used, free space and filesystem type.", {}, self.name),
            MCPTool("get_battery_info", "Battery percentage, charging state, and estimated time remaining.", {}, self.name),
            MCPTool("get_network_info", "All network adapters with IP addresses, MAC, and connection status.", {}, self.name),
            MCPTool("get_windows_version", "Windows edition, version number, build number, and architecture.", {}, self.name),
            MCPTool("get_hardware_info", "CPU model, RAM modules, motherboard, GPU(s), and BIOS version.", {}, self.name),
            MCPTool(
                "get_installed_apps",
                "List installed applications discoverable via registry.",
                {},
                self.name,
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        t0 = time.monotonic()
        try:
            content = self._dispatch(name, arguments)
            self._audit.log(
                session_id="",
                server=self.name,
                tool=name,
                tier=1,
                arguments=arguments,
                confirmation_status="not_required",
                outcome="success",
                duration_s=round(time.monotonic() - t0, 4),
            )
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content=content,
                duration_s=round(time.monotonic() - t0, 3),
            )
        except Exception as exc:
            duration = round(time.monotonic() - t0, 3)
            self._audit.log(
                session_id="",
                server=self.name,
                tool=name,
                tier=1,
                arguments=arguments,
                confirmation_status="not_required",
                outcome="error",
                duration_s=duration,
                error=str(exc),
            )
            return MCPCallResult(
                tool_name=name,
                server_name=self.name,
                content=str(exc),
                is_error=True,
                duration_s=duration,
            )

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if not _WINDOWS_ONLY:
            return _WIN_ERR
        if name == "get_cpu_info":
            return self._get_cpu_info()
        if name == "get_ram_info":
            return self._get_ram_info()
        if name == "get_disk_info":
            return self._get_disk_info()
        if name == "get_battery_info":
            return self._get_battery_info()
        if name == "get_network_info":
            return self._get_network_info()
        if name == "get_windows_version":
            return self._get_windows_version()
        if name == "get_hardware_info":
            return self._get_hardware_info()
        if name == "get_installed_apps":
            return self._get_installed_apps()
        raise ValueError(f"Unknown tool '{name}'")

    def _get_cpu_info(self) -> str:
        try:
            import psutil
        except ImportError:
            return _IMPORT_ERR
        count_physical = psutil.cpu_count(logical=False) or 0
        count_logical = psutil.cpu_count(logical=True) or 0
        overall = psutil.cpu_percent(interval=0.5)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        freq = psutil.cpu_freq()
        lines = [
            "CPU Information",
            "─" * 50,
            f"Physical cores: {count_physical} ({count_logical} logical)",
        ]
        if freq:
            lines.append(f"Current speed:  {freq.current:.0f} MHz  Max: {freq.max:.0f} MHz")
        lines.append(f"\nOverall usage:  {overall:.1f}%")
        if per_core:
            for i, pct in enumerate(per_core):
                if i % 4 == 0 and i > 0:
                    lines.append("")
                lines.append(f"  Core {i:<3}: {pct:5.1f}%")
        return "\n".join(lines)

    def _get_ram_info(self) -> str:
        try:
            import psutil
        except ImportError:
            return _IMPORT_ERR
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()

        def _fmt(b: int) -> str:
            gb = b / (1024 ** 3)
            return f"{gb:.2f} GB"

        return (
            "RAM Information\n" + "─" * 50 + "\n"
            f"Total:    {_fmt(vm.total)}\n"
            f"Used:     {_fmt(vm.used)}  ({vm.percent:.1f}%)\n"
            f"Free:     {_fmt(vm.available)}\n"
            f"Swap:     {_fmt(swap.total)} total  {_fmt(swap.used)} used"
        )

    def _get_disk_info(self) -> str:
        try:
            import psutil
        except ImportError:
            return _IMPORT_ERR
        lines = ["Disk Information", "─" * 60]
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                total_gb = usage.total / (1024 ** 3)
                used_gb = usage.used / (1024 ** 3)
                free_gb = usage.free / (1024 ** 3)
                lines.append(
                    f"{part.device:<12} ({part.fstype})  "
                    f"Total: {total_gb:.1f} GB  "
                    f"Used: {used_gb:.1f} GB  "
                    f"Free: {free_gb:.1f} GB  "
                    f"({usage.percent:.1f}%)"
                )
            except PermissionError:
                lines.append(f"{part.device:<12} (access denied)")
        return "\n".join(lines)

    def _get_battery_info(self) -> str:
        try:
            import psutil
        except ImportError:
            return _IMPORT_ERR
        battery = psutil.sensors_battery()
        if battery is None:
            return "No battery detected (desktop system or battery info unavailable)."
        charging = "Charging" if battery.power_plugged else "Discharging"
        secs = battery.secsleft
        if secs == psutil.POWER_TIME_UNLIMITED:
            remaining = "unlimited (plugged in)"
        elif secs == psutil.POWER_TIME_UNKNOWN:
            remaining = "unknown"
        else:
            h, m = divmod(secs // 60, 60)
            remaining = f"{h}h {m}m"
        return (
            "Battery Information\n" + "─" * 40 + "\n"
            f"Level:     {battery.percent:.1f}%\n"
            f"Status:    {charging}\n"
            f"Remaining: {remaining}"
        )

    def _get_network_info(self) -> str:
        try:
            import psutil
        except ImportError:
            return _IMPORT_ERR
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        lines = ["Network Adapters", "─" * 60]
        for iface, addr_list in addrs.items():
            stat = stats.get(iface)
            status = "UP" if stat and stat.isup else "DOWN"
            lines.append(f"\n{iface}  [{status}]")
            for addr in addr_list:
                if addr.family.name == "AF_INET":
                    lines.append(f"  IPv4:  {addr.address}  mask: {addr.netmask}")
                elif addr.family.name == "AF_INET6":
                    lines.append(f"  IPv6:  {addr.address}")
                elif addr.family.name == "AF_LINK":
                    lines.append(f"  MAC:   {addr.address}")
        return "\n".join(lines)

    def _get_windows_version(self) -> str:
        import platform
        ver = platform.version()
        machine = platform.machine()
        try:
            wv = sys.getwindowsversion()  # type: ignore[attr-defined]
            build = wv.build
            major = wv.major
            minor = wv.minor
        except AttributeError:
            build = major = minor = "unknown"
        return (
            "Windows Version\n" + "─" * 40 + "\n"
            f"Version:      {ver}\n"
            f"Build:        {build}\n"
            f"Major.Minor:  {major}.{minor}\n"
            f"Architecture: {machine}"
        )

    def _get_hardware_info(self) -> str:
        lines = ["Hardware Information", "─" * 50]
        try:
            import winreg  # type: ignore[import]
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            cpu_name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            lines.append(f"CPU:   {cpu_name.strip()}")
        except Exception:
            lines.append("CPU:   (unavailable)")
        try:
            import psutil
            vm = psutil.virtual_memory()
            lines.append(f"RAM:   {vm.total / (1024**3):.1f} GB total")
        except ImportError:
            lines.append("RAM:   (psutil not installed)")
        try:
            import winreg  # type: ignore[import]
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\BIOS",
            )
            bios_vendor, _ = winreg.QueryValueEx(key, "BIOSVendor")
            bios_ver, _ = winreg.QueryValueEx(key, "BIOSVersion")
            winreg.CloseKey(key)
            lines.append(f"BIOS:  {bios_vendor} {bios_ver}")
        except Exception:
            lines.append("BIOS:  (unavailable)")
        return "\n".join(lines)

    def _get_installed_apps(self) -> str:
        apps: list[str] = []
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
                                name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                                if name and name not in apps:
                                    apps.append(str(name))
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
            return "winreg not available (Windows-only)."

        apps.sort(key=str.lower)
        lines = [f"Installed Applications ({len(apps)} found)", "─" * 50]
        lines.extend(apps[:200])
        if len(apps) > 200:
            lines.append(f"... and {len(apps) - 200} more")
        return "\n".join(lines)
