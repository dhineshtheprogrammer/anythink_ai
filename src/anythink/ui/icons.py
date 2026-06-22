"""Unified monochrome icon language for the Anythink terminal UI.

Every icon is a plain Unicode glyph or ASCII fallback — no emoji with baked-in
font colors.  Use ``get_icon(key, config)`` everywhere an icon is needed so
the entire UI switches consistently when the user changes Icon Style in settings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anythink.config.schema import AppConfig

ICONS_UNICODE: dict[str, str | list[str]] = {
    "search": "⌕",
    "rag": "⌬",
    "attachment": "⎘",
    "image": "▦",
    "success": "✓",
    "error": "✕",
    "warning": "▲",
    "branch": "⎇",
    "bookmark": "★",
    "notify": "◆",
    "tool": "⚙",
    "mcp": "▹",
    "dot": "●",
    "record": "●",
    "settings": "⚙",
    "copy": "⧉",
    "stop": "■",
    "tip": "◆",
    "info": "◈",
    "rag_footer": "⌬",
    "spinner": ["◐", "◓", "◑", "◒"],
}

ICONS_ASCII: dict[str, str | list[str]] = {
    "search": "[S]",
    "rag": "[R]",
    "attachment": "[F]",
    "image": "[I]",
    "success": "[+]",
    "error": "[x]",
    "warning": "[!]",
    "branch": "[B]",
    "bookmark": "[*]",
    "notify": "[N]",
    "tool": "[T]",
    "mcp": "[>]",
    "dot": "o",
    "record": "o",
    "settings": "[S]",
    "copy": "[C]",
    "stop": "[.]",
    "tip": "[>]",
    "info": "[i]",
    "rag_footer": "[R]",
    "spinner": ["|", "/", "-", "\\"],
}


def get_icon(key: str, config: AppConfig | None = None) -> str:
    """Return the glyph for *key* based on the active icon style."""
    use_unicode = config is None or config.icon_style == "unicode"
    table = ICONS_UNICODE if use_unicode else ICONS_ASCII
    val = table.get(key, "?")
    return val[0] if isinstance(val, list) else val


def get_spinner_frames(config: AppConfig | None = None) -> list[str]:
    """Return the list of spinner animation frames for the active icon style."""
    use_unicode = config is None or config.icon_style == "unicode"
    frames = ICONS_UNICODE["spinner"] if use_unicode else ICONS_ASCII["spinner"]
    return list(frames)  # type: ignore[arg-type]
