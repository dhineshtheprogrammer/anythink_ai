"""Path permission guard for Windows MCP filesystem operations."""

from __future__ import annotations

import os
from pathlib import Path

from anythink.config.schema import AppConfig

# System-critical paths that can never be granted access, regardless of the
# user-configured allowed list. Stored lowercase for case-insensitive matching.
_NON_REMOVABLE_BLOCKED: frozenset[str] = frozenset(
    {
        "c:\\windows\\",
        "c:\\windows\\system32\\",
        "c:\\windows\\syswow64\\",
        "c:\\program files\\",
        "c:\\program files (x86)\\",
        "c:\\programdata\\microsoft\\",
    }
)


def _normalize(path: str) -> str:
    """Resolve, absolutize, and lowercase a path for comparison."""
    return os.path.normcase(os.path.abspath(path)) + os.sep


def _default_allowed() -> list[str]:
    home = str(Path.home())
    return [
        os.path.join(home, "Documents") + os.sep,
        os.path.join(home, "Desktop") + os.sep,
        os.path.join(home, "Downloads") + os.sep,
    ]


def _default_blocked() -> list[str]:
    home = str(Path.home())
    appdata = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
    localappdata = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    return [
        os.path.join(appdata, "Microsoft") + os.sep,
        os.path.join(localappdata, "Microsoft") + os.sep,
        # Block the anythink package install dir if detectable
    ]


class WindowsPathGuard:
    """Validates all filesystem operation paths against allowed/blocked lists.

    Blocked paths always take priority over allowed paths. The
    `_NON_REMOVABLE_BLOCKED` set can never be modified at runtime.
    """

    def __init__(self, config: AppConfig) -> None:
        if config.windows_allowed_paths:
            self._allowed: list[str] = [_normalize(p) for p in config.windows_allowed_paths]
        else:
            self._allowed = [_normalize(p) for p in _default_allowed()]

        if config.windows_blocked_paths:
            self._blocked: list[str] = [_normalize(p) for p in config.windows_blocked_paths]
        else:
            self._blocked = [_normalize(p) for p in _default_blocked()]

    # ------------------------------------------------------------------
    # Core validation
    # ------------------------------------------------------------------

    def validate(self, path: str) -> str | None:
        """Return an error message if *path* is not permitted, else None.

        Checks (in order):
        1. Non-removable system-critical blocked prefixes
        2. User-configured blocked prefixes
        3. User-configured allowed prefixes (must match at least one)
        """
        normalized = _normalize(path)

        for blocked in _NON_REMOVABLE_BLOCKED:
            if normalized.startswith(blocked):
                return (
                    f"Access denied: '{path}' is within a protected system directory "
                    f"({blocked.rstrip(os.sep)}) and cannot be accessed by AI tools."
                )

        for blocked in self._blocked:
            if normalized.startswith(blocked):
                return (
                    f"Access denied: '{path}' is within a blocked path "
                    f"({blocked.rstrip(os.sep)})."
                )

        for allowed in self._allowed:
            if normalized.startswith(allowed):
                return None

        return (
            f"Access denied: '{path}' is not within any allowed path. "
            f"Use '/mcp windows paths allow <path>' to grant access."
        )

    # ------------------------------------------------------------------
    # Runtime list management (callers persist changes via config replace)
    # ------------------------------------------------------------------

    def add_allowed(self, path: str) -> None:
        normalized = _normalize(path)
        if normalized not in self._allowed:
            self._allowed.append(normalized)

    def remove_allowed(self, path: str) -> bool:
        normalized = _normalize(path)
        try:
            self._allowed.remove(normalized)
            return True
        except ValueError:
            return False

    def add_blocked(self, path: str) -> None:
        normalized = _normalize(path)
        if normalized not in self._blocked:
            self._blocked.append(normalized)

    def remove_blocked(self, path: str) -> bool:
        """Remove a user-configured blocked path. Non-removable system paths are rejected."""
        normalized = _normalize(path)
        if normalized in _NON_REMOVABLE_BLOCKED:
            return False
        try:
            self._blocked.remove(normalized)
            return True
        except ValueError:
            return False

    @property
    def allowed_paths(self) -> list[str]:
        return list(self._allowed)

    @property
    def blocked_paths(self) -> list[str]:
        return list(self._blocked)

    @property
    def system_blocked_paths(self) -> list[str]:
        return sorted(_NON_REMOVABLE_BLOCKED)
