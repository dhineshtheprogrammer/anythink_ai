"""Timestamp formatting with relative / absolute modes."""

from __future__ import annotations

import sys
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anythink.config.schema import AppConfig

# strftime day-of-month without zero-padding differs by platform
_DAY_FMT = "%#d" if sys.platform == "win32" else "%-d"


def format_timestamp(dt: datetime, config: AppConfig | None = None) -> str:
    """Return a human-readable timestamp string for *dt*.

    In relative mode (default) the string is context-sensitive:
        - Under 1 min  → "just now"
        - 1–59 min     → "Xm ago"
        - 1–23 h       → "Xh ago"
        - Yesterday    → "Yesterday, HH:MM"
        - Same year    → "Mon D, HH:MM"
        - Older        → "Mon D YYYY, HH:MM"

    In absolute mode (config.timestamps == "absolute"), returns "HH:MM:SS".
    """
    if config is not None and config.timestamps == "absolute":
        return dt.strftime("%H:%M:%S")

    now = datetime.now()
    delta = now - dt
    seconds = delta.total_seconds()

    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"

    days_diff = (now.date() - dt.date()).days
    if days_diff == 1:
        return f"Yesterday, {dt.strftime('%H:%M')}"
    if dt.year == now.year:
        return dt.strftime(f"%b {_DAY_FMT}, %H:%M")
    return dt.strftime(f"%b {_DAY_FMT} %Y, %H:%M")
