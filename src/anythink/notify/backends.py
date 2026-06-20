"""Platform-specific notification backends.

Each backend attempts to deliver a desktop notification using the native
mechanism for its platform. All failures are silently swallowed — notifications
are always best-effort.
"""

from __future__ import annotations

import shutil
import sys
from abc import ABC, abstractmethod


class BaseNotificationBackend(ABC):
    """Abstract base for a platform notification backend."""

    @abstractmethod
    def send(self, title: str, message: str) -> None:
        """Deliver a desktop notification with *title* and *message*."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when this backend can deliver notifications here."""


class WindowsBackend(BaseNotificationBackend):
    """Windows Toast notifications via PowerShell (no extra deps)."""

    def is_available(self) -> bool:
        return sys.platform == "win32"

    def send(self, title: str, message: str) -> None:
        import subprocess  # noqa: PLC0415  # nosec B404 - notifications are best-effort; fixed args

        # Use PowerShell's Windows.UI.Notifications API (available on Windows 10+).
        # Title and message are injected as PowerShell string literals; we escape
        # single-quotes to prevent injection. B603/B607: powershell is resolved
        # by the OS; no user shell; no shell=True; args are a fixed list.
        safe_title = title.replace("'", "''")
        safe_msg = message.replace("'", "''")
        ps_script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
            " ContentType = WindowsRuntime] | Out-Null; "
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument,"
            " ContentType = WindowsRuntime] | Out-Null; "
            "$xml = [Windows.Data.Xml.Dom.XmlDocument]::new(); "
            '$xml.LoadXml(\'<toast><visual><binding template="ToastText02">'
            f'<text id="1">{safe_title}</text>'
            f'<text id="2">{safe_msg}</text>'
            "</binding></visual></toast>'); "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
            "[Windows.UI.Notifications.ToastNotificationManager]::"
            "CreateToastNotifier('Anythink').Show($toast)"
        )
        subprocess.run(  # nosec B603 B607
            ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            timeout=8,
            check=False,
        )


class MacOSBackend(BaseNotificationBackend):
    """macOS Notification Center via ``osascript``."""

    def is_available(self) -> bool:
        return sys.platform == "darwin" and bool(shutil.which("osascript"))

    def send(self, title: str, message: str) -> None:
        import subprocess  # noqa: PLC0415  # nosec B404

        # Title/message passed as separate argv elements — no shell expansion.
        # B603/B607: osascript resolved by OS; no shell=True; fixed argv structure.
        safe_title = title.replace('"', '\\"')
        safe_msg = message.replace('"', '\\"')
        subprocess.run(  # nosec B603 B607
            [
                "osascript",
                "-e",
                f'display notification "{safe_msg}" with title "{safe_title}"',
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )


class LinuxBackend(BaseNotificationBackend):
    """Linux desktop notifications via ``notify-send``."""

    def is_available(self) -> bool:
        return sys.platform.startswith("linux") and bool(shutil.which("notify-send"))

    def send(self, title: str, message: str) -> None:
        import subprocess  # noqa: PLC0415  # nosec B404

        # Title and message are discrete argv elements — no shell injection.
        # B603/B607: notify-send resolved by OS; no shell=True; each value is
        # a separate element.
        subprocess.run(  # nosec B603 B607
            ["notify-send", "--app-name=Anythink", "--expire-time=5000", title, message],
            capture_output=True,
            timeout=5,
            check=False,
        )


class NullBackend(BaseNotificationBackend):
    """Silent no-op backend used when no platform backend is detected."""

    def is_available(self) -> bool:
        return True

    def send(self, title: str, message: str) -> None:
        pass


def detect_backend() -> BaseNotificationBackend:
    """Return the first available backend for the current platform."""
    for cls in (WindowsBackend, MacOSBackend, LinuxBackend):
        b = cls()
        if b.is_available():
            return b
    return NullBackend()
