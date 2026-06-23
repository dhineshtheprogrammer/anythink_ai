"""Startup experience helpers: returning-user detection and session resume."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from anythink import __version__

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.session.models import Session


# Minimum non-system messages for a session to be considered "resumable"
_MIN_EXCHANGE_MESSAGES = 2


def is_returning_user(ctx: AppContext) -> bool:
    """Return True if the user has any prior saved sessions."""
    try:
        sessions = ctx.session_manager.list_sessions()
        return len(sessions) > 0
    except Exception:
        return False


def find_resumable_session(ctx: AppContext) -> Session | None:
    """Return the most-recent session if it looks mid-conversation.

    A session is resumable when it has at least two non-system messages
    (i.e. at least one complete user+assistant exchange was captured).
    """
    try:
        sessions = ctx.session_manager.list_sessions()
    except Exception:
        return None

    if not sessions:
        return None

    most_recent = sessions[0]  # already sorted by updated_at DESC
    non_system = [m for m in most_recent.messages if m.role != "system"]
    if len(non_system) >= _MIN_EXCHANGE_MESSAGES:
        return most_recent
    return None


def startup_one_liner(ctx: AppContext) -> str:
    """Compact single-line status shown on startup for returning users."""
    model_alias = ctx.config.default_model_alias or "—"
    ctx_size: str
    try:
        alias = ctx.model_registry.get(model_alias)
        ctx_size = f"{alias.context_window:,}" if alias else "—"
        provider = alias.provider if alias else "—"
    except Exception:
        ctx_size = "—"
        provider = "—"

    return (
        f" ✦ Anythink v{__version__}"
        f"  ·  {model_alias} ({provider.capitalize()})"
        f"  ·  {ctx_size} ctx"
        "  ·  Type /help for commands"
    )


def terminal_supports_unicode() -> bool:
    """Return False for known-ASCII terminals; True otherwise."""
    term = os.environ.get("TERM", "")
    if term in ("dumb", "vt100"):
        return False
    lang = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    if lang and "UTF" not in lang.upper():
        return False
    if os.environ.get("WT_SESSION"):
        return True
    if os.environ.get("TERM_PROGRAM") in ("iTerm.app", "WezTerm", "Hyper", "vscode"):
        return True
    if os.environ.get("COLORTERM") in ("truecolor", "24bit"):
        return True
    if os.environ.get("VTE_VERSION"):
        return True
    return True


def apply_icon_style_heuristic(ctx: AppContext) -> None:
    """Auto-downgrade icon_style to ascii for terminals that can't render Unicode."""
    if ctx.config.icon_style == "ascii":
        return
    if not terminal_supports_unicode():
        from dataclasses import replace as _replace

        ctx.config = _replace(ctx.config, icon_style="ascii")
