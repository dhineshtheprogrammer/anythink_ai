"""Windows Notification MCP server — send Windows toast notifications."""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from typing import Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.safety import WindowsSafetyChecker

_WINDOWS_ONLY = sys.platform == "win32"
_WIN_ERR = f"This tool requires Windows. Current platform: {sys.platform}"


class WindowsNotificationServer(BuiltinMCPServer):
    """Send Windows desktop toast notifications on the user's behalf."""

    name = "windows-notification"
    description = "Send Windows desktop toast notifications on the user's behalf."

    def __init__(
        self,
        safety: WindowsSafetyChecker,
        audit: WindowsAuditLog,
        app_name: str = "Anythink",
    ) -> None:
        self._safety = safety
        self._audit = audit
        self._app_name = app_name
        # Maps notification_id -> asyncio.Task for scheduled notifications
        self._scheduled: dict[str, asyncio.Task[None]] = {}

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                "send_notification",
                "Send an immediate Windows toast notification.",
                {
                    "title": {"type": "string", "description": "Notification heading"},
                    "message": {"type": "string", "description": "Notification body text"},
                    "icon": {"type": "string", "description": "Path to .ico/.png icon (optional)"},
                },
                self.name,
            ),
            MCPTool(
                "send_scheduled_notification",
                "Send a notification after a delay or at a specific time.",
                {
                    "title": {"type": "string", "description": "Notification heading"},
                    "message": {"type": "string", "description": "Notification body text"},
                    "delay_seconds": {"type": "integer", "description": "Seconds to wait before sending (optional)"},
                    "at_time": {"type": "string", "description": "HH:MM time string for scheduled send (optional)"},
                },
                self.name,
            ),
            MCPTool(
                "list_scheduled_notifications",
                "List all pending scheduled notifications.",
                {},
                self.name,
            ),
            MCPTool(
                "cancel_scheduled_notification",
                "Cancel a pending scheduled notification by ID.",
                {"notification_id": {"type": "string", "description": "Notification ID from list_scheduled_notifications"}},
                self.name,
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        t0 = time.monotonic()
        tier = self._safety.get_tier(self.name, name, **arguments)
        try:
            if name == "send_scheduled_notification":
                content = await self._send_scheduled(
                    title=str(arguments.get("title", self._app_name)),
                    message=str(arguments.get("message", "")),
                    delay_seconds=arguments.get("delay_seconds"),
                    at_time=arguments.get("at_time"),
                )
            else:
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
        if name == "send_notification":
            return self._send_now(
                title=str(arguments.get("title", self._app_name)),
                message=str(arguments.get("message", "")),
                icon=arguments.get("icon"),
            )
        if name == "list_scheduled_notifications":
            return self._list_scheduled()
        if name == "cancel_scheduled_notification":
            return self._cancel_scheduled(str(arguments.get("notification_id", "")))
        raise ValueError(f"Unknown tool '{name}'")

    def _send_now(self, title: str, message: str, icon: str | None = None) -> str:
        # Try winotify first (modern Windows 10/11 toast API)
        try:
            from winotify import Notification  # type: ignore[import]
            n = Notification(
                app_id=self._app_name,
                title=title,
                msg=message,
                icon=icon or "",
            )
            n.show()
            return f"Notification sent: '{title}'"
        except ImportError:
            pass

        # Fallback: win10toast
        try:
            from win10toast import ToastNotifier  # type: ignore[import]
            ToastNotifier().show_toast(
                title,
                message,
                duration=5,
                threaded=True,
            )
            return f"Notification sent (win10toast): '{title}'"
        except ImportError:
            pass

        # Final fallback: PowerShell
        # Escape single quotes to prevent PS string breakage (PS escapes ' as '')
        import subprocess
        ps_title = title.replace("'", "''")
        ps_message = message.replace("'", "''")
        ps_app_name = self._app_name.replace("'", "''")
        ps = (
            f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            f"ContentType = WindowsRuntime] | Out-Null;"
            f"$t = [Windows.UI.Notifications.ToastTemplateType]::ToastText02;"
            f"$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($t);"
            f"$x.GetElementsByTagName('text')[0].AppendChild($x.CreateTextNode('{ps_title}')) | Out-Null;"
            f"$x.GetElementsByTagName('text')[1].AppendChild($x.CreateTextNode('{ps_message}')) | Out-Null;"
            f"$n = [Windows.UI.Notifications.ToastNotification]::new($x);"
            f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{ps_app_name}').Show($n)"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return f"Notification sent (PowerShell): '{title}'"
        except Exception:
            pass
        return (
            "Could not send notification. "
            "Install winotify: pip install anythink[windows]"
        )

    async def _send_scheduled(
        self,
        title: str,
        message: str,
        delay_seconds: Any,
        at_time: Any,
    ) -> str:
        if not _WINDOWS_ONLY:
            return _WIN_ERR
        if delay_seconds is not None:
            delay = float(delay_seconds)
        elif at_time is not None:
            delay = self._parse_at_time(str(at_time))
            if delay < 0:
                return f"Scheduled time '{at_time}' is in the past."
        else:
            return "Provide either 'delay_seconds' or 'at_time'."

        notification_id = str(uuid.uuid4())[:8]

        async def _send_after() -> None:
            await asyncio.sleep(delay)
            self._send_now(title, message)
            self._scheduled.pop(notification_id, None)

        task = asyncio.get_event_loop().create_task(_send_after())
        self._scheduled[notification_id] = task
        mins = int(delay) // 60
        secs = int(delay) % 60
        when_str = f"{mins}m {secs}s" if mins else f"{secs}s"
        return (
            f"Notification scheduled in {when_str}. "
            f"ID: {notification_id}"
        )

    def _parse_at_time(self, at_time: str) -> float:
        """Parse time string and return seconds until that time.

        Supported formats: "14:30", "2:30 PM", "tomorrow 14:30", "tomorrow 2:30 PM".
        Returns -1.0 on parse failure.
        """
        import datetime
        now = datetime.datetime.now()
        text = at_time.strip().lower()
        add_day = text.startswith("tomorrow")
        if add_day:
            text = text.replace("tomorrow", "", 1).strip()
        is_pm = text.endswith("pm")
        is_am = text.endswith("am")
        if is_pm or is_am:
            text = text[:-2].strip()
        try:
            parts = text.split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            if is_pm and h != 12:
                h += 12
            if is_am and h == 12:
                h = 0
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if add_day:
                target += datetime.timedelta(days=1)
            diff = (target - now).total_seconds()
            if diff < 0 and not add_day:
                diff += 86400  # roll to next day
            return diff
        except Exception:
            return -1.0

    def _list_scheduled(self) -> str:
        if not self._scheduled:
            return "No pending scheduled notifications."
        lines = [f"Scheduled Notifications ({len(self._scheduled)})", "─" * 50]
        for nid, task in self._scheduled.items():
            status = "pending" if not task.done() else "done"
            lines.append(f"  ID: {nid}  Status: {status}")
        return "\n".join(lines)

    def _cancel_scheduled(self, notification_id: str) -> str:
        task = self._scheduled.pop(notification_id, None)
        if task is None:
            return f"No scheduled notification with ID '{notification_id}'."
        task.cancel()
        return f"Scheduled notification '{notification_id}' cancelled."
