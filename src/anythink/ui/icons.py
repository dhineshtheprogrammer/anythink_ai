"""Unified monochrome icon language for the Anythink terminal UI.

Every icon is a plain Unicode glyph or ASCII fallback — no emoji with baked-in
font colors.  Use ``get_icon(key, config)`` everywhere an icon is needed so
the entire UI switches consistently when the user changes Icon Style in settings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anythink.config.schema import AppConfig

# U+FE0E — forces text (monochrome, single-cell) presentation for emoji-default glyphs.
VS15 = "︎"

ICONS_UNICODE: dict[str, str | list[str]] = {
    "search": "⌕",
    "rag": "⌬",
    "attachment": "⎘",
    "image": "▦",
    "success": "✓",
    "error": "✕",
    "warning": "▲",
    "branch": "⎇",
    "bookmark": "★" + VS15,
    "notify": "◆",
    "tool": "⚙" + VS15,
    "mcp": "▹",
    "dot": "●",
    "record": "●",
    "settings": "⚙" + VS15,
    "copy": "⧉",
    "stop": "■",
    "tip": "◆",
    "info": "◈",
    "rag_footer": "⌬",
    "timer": "⏱" + VS15,
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
    "timer": "[T]",
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
    assert isinstance(frames, list)
    return list(frames)


def patch_rich_cell_len() -> None:
    """Patch Rich's cell_len so (glyph + VS15) counts as exactly 1 cell wide."""
    import rich.cells

    _orig = rich.cells.cell_len

    def _patched(text: str) -> int:
        if VS15 not in text:
            return _orig(text)
        total = 0
        i = 0
        while i < len(text):
            if i + 1 < len(text) and text[i + 1] == VS15:
                total += 1
                i += 2
            else:
                total += _orig(text[i])
                i += 1
        return total

    rich.cells.cell_len = _patched  # type: ignore[assignment]
    if hasattr(rich.cells, "cached_cell_len"):
        rich.cells.cached_cell_len.cache_clear()
