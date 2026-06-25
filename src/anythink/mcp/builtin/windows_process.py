"""Windows Process MCP server — list, start, and stop Windows processes."""

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

# Accounts whose processes are always protected from kill operations
_PROTECTED_ACCOUNTS = frozenset(
    {
        "nt authority\\system",
        "nt authority\\local service",
        "nt authority\\network service",
    }
)


class WindowsProcessServer(BuiltinMCPServer):
    """List, start, and stop Windows processes."""

    name = "windows-process"
    description = "List, start, and stop Windows processes."

    def __init__(
        self,
        safety: WindowsSafetyChecker,
        audit: WindowsAuditLog,
        blocked_apps: tuple[str, ...] = ("regedit.exe", "cmd.exe", "powershell.exe", "mmc.exe"),
    ) -> None:
        self._safety = safety
        self._audit = audit
        self._blocked_apps = frozenset(a.lower() for a in blocked_apps)

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                "list_processes",
                "List all running processes with PID, name, CPU%, and RAM usage.",
                {},
                self.name,
            ),
            MCPTool(
                "get_process_info",
                "Get detailed info for a specific process by PID or name.",
                {
                    "pid": {"type": "integer", "description": "Process ID (optional if name given)"},
                    "name": {"type": "string", "description": "Process name (optional if pid given)"},
                },
                self.name,
            ),
            MCPTool(
                "start_process",
                "Start a new process by executable path or command string.",
                {
                    "command": {"type": "string", "description": "Executable path or command"},
                    "args": {"type": "array", "description": "Additional arguments", "default": []},
                    "working_dir": {"type": "string", "description": "Working directory (optional)"},
                    "detached": {"type": "boolean", "description": "Run detached (default: true)", "default": True},
                },
                self.name,
            ),
            MCPTool(
                "kill_process",
                "Terminate a process by PID or name (graceful first, then force).",
                {
                    "pid": {"type": "integer", "description": "Process ID (optional if name given)"},
                    "name": {"type": "string", "description": "Process name (optional if pid given)"},
                    "force": {"type": "boolean", "description": "Force kill if graceful fails", "default": False},
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
        if name == "list_processes":
            return self._list_processes()
        if name == "get_process_info":
            return self._get_process_info(
                pid=arguments.get("pid"),
                proc_name=arguments.get("name"),
            )
        if name == "start_process":
            return self._start_process(
                command=str(arguments.get("command", "")),
                args=list(arguments.get("args", [])),
                working_dir=arguments.get("working_dir"),
                detached=bool(arguments.get("detached", True)),
            )
        if name == "kill_process":
            return self._kill_process(
                pid=arguments.get("pid"),
                proc_name=arguments.get("name"),
                force=bool(arguments.get("force", False)),
            )
        raise ValueError(f"Unknown tool '{name}'")

    def _list_processes(self) -> str:
        try:
            import psutil
        except ImportError:
            return "psutil not installed. Run: pip install anythink[windows]"

        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                procs.append(p.info)  # type: ignore[attr-defined]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)

        lines = [
            f"Running Processes ({len(procs)} total)",
            "─" * 70,
            f"{'PID':<8} {'Name':<28} {'CPU%':>6} {'RAM%':>6}  Status",
            "─" * 70,
        ]
        for p in procs[:50]:
            cpu = p.get("cpu_percent") or 0
            mem = p.get("memory_percent") or 0
            lines.append(
                f"{p.get('pid', '')!s:<8} {(p.get('name') or ''):<28} "
                f"{cpu:>5.1f}% {mem:>5.1f}%  {p.get('status', '')}"
            )
        if len(procs) > 50:
            lines.append(f"... and {len(procs) - 50} more processes (showing top 50 by CPU)")
        return "\n".join(lines)

    def _get_process_info(self, pid: Any, proc_name: Any) -> str:
        try:
            import psutil
        except ImportError:
            return "psutil not installed. Run: pip install anythink[windows]"

        if pid is not None:
            try:
                proc = psutil.Process(int(pid))
            except psutil.NoSuchProcess:
                return f"No process with PID {pid} found."
        elif proc_name:
            matches = [
                p for p in psutil.process_iter(["name"])
                if (p.info.get("name") or "").lower() == str(proc_name).lower()  # type: ignore[attr-defined]
            ]
            if not matches:
                return f"No process named '{proc_name}' found."
            proc = matches[0]
        else:
            return "Provide either 'pid' or 'name'."

        try:
            with proc.oneshot():
                name = proc.name()
                pid_val = proc.pid
                status = proc.status()
                cpu = proc.cpu_percent(interval=0.2)
                mem_mb = proc.memory_info().rss / (1024 * 1024)
                try:
                    username = proc.username()
                except Exception:
                    username = "(access denied)"
                try:
                    cmdline = " ".join(proc.cmdline())
                except Exception:
                    cmdline = "(unavailable)"
            return (
                f"Process: {name}  (PID {pid_val})\n"
                f"Status:  {status}\n"
                f"CPU:     {cpu:.1f}%\n"
                f"RAM:     {mem_mb:.1f} MB\n"
                f"User:    {username}\n"
                f"Cmd:     {cmdline}"
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            return f"Could not retrieve process info: {e}"

    def _start_process(
        self,
        command: str,
        args: list[str],
        working_dir: str | None,
        detached: bool,
    ) -> str:
        import os

        exe_name = os.path.basename(command).lower()
        if exe_name in self._blocked_apps:
            return (
                f"Cannot launch '{exe_name}': it is on the blocked applications list. "
                "Use '/mcp windows apps unblock <name>' to remove it."
            )
        cmd = [command] + [str(a) for a in args]
        flags = 0
        if detached and sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        if detached:
            proc = subprocess.Popen(
                cmd,
                cwd=working_dir,
                creationflags=flags,
                close_fds=True,
            )
            return f"Process started with PID {proc.pid}."
        else:
            result = subprocess.run(
                cmd,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = (result.stdout + result.stderr)[:5000]
            return (
                f"Process exited with code {result.returncode}.\n"
                f"Output:\n{output}"
            )

    def _kill_process(self, pid: Any, proc_name: Any, force: bool) -> str:
        try:
            import psutil
        except ImportError:
            return "psutil not installed. Run: pip install anythink[windows]"

        if pid is not None:
            try:
                procs = [psutil.Process(int(pid))]
            except psutil.NoSuchProcess:
                return f"No process with PID {pid} found."
        elif proc_name:
            procs = [
                p for p in psutil.process_iter(["name"])
                if (p.info.get("name") or "").lower() == str(proc_name).lower()  # type: ignore[attr-defined]
            ]
            if not procs:
                return f"No process named '{proc_name}' found."
        else:
            return "Provide either 'pid' or 'name'."

        results = []
        for proc in procs:
            try:
                try:
                    username = proc.username().lower()
                except Exception:
                    username = ""
                if username in _PROTECTED_ACCOUNTS:
                    results.append(
                        f"PID {proc.pid} ({proc.name()}): Protected — owned by system account '{username}'. "
                        "Cannot be terminated."
                    )
                    continue

                proc.terminate()
                try:
                    proc.wait(timeout=5)
                    results.append(f"PID {proc.pid} ({proc.name()}): Terminated gracefully.")
                except psutil.TimeoutExpired:
                    if force:
                        proc.kill()
                        results.append(f"PID {proc.pid} ({proc.name()}): Force-killed (SIGKILL).")
                    else:
                        results.append(
                            f"PID {proc.pid} ({proc.name()}): Did not terminate gracefully in 5s. "
                            "Use force=true to force-kill."
                        )
            except psutil.NoSuchProcess:
                results.append(f"PID {proc.pid}: Process no longer exists.")
            except psutil.AccessDenied:
                results.append(f"PID {proc.pid} ({proc.name() if hasattr(proc, 'name') else ''}): Access denied.")

        return "\n".join(results)
