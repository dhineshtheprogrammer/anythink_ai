"""Maps Anythink Theme color tokens to CSS hex values for Textual styling."""

from __future__ import annotations

from anythink.ui.theme import Theme

# Rich named colors → CSS hex values (terminal palette approximations)
_RICH_TO_HEX: dict[str, str] = {
    "bright_cyan": "#00ffff",
    "cyan": "#00cdcd",
    "bright_blue": "#0000ff",
    "grey58": "#949494",
    "bright_red": "#ff0000",
    "bright_yellow": "#ffff00",
    "bright_green": "#00ff00",
    "bright_magenta": "#ff00ff",
    "magenta": "#cd00cd",
    "grey54": "#8a8a8a",
    "red": "#cd0000",
    "dark_orange": "#ff8c00",
    "green": "#00cd00",
    "white": "#e3e3e3",
    "bright_white": "#ffffff",
    "grey70": "#b2b2b2",
    "grey46": "#767676",
}


def resolve(rich_color: str) -> str:
    """Convert a Rich named color to a CSS hex string.

    Falls back to the input string unchanged if it's not a named color
    (e.g. it's already a hex value).
    """
    return _RICH_TO_HEX.get(rich_color, rich_color)


def theme_css_vars(theme: Theme) -> str:
    """Return a Textual CSS snippet declaring $primary / $accent / $muted etc."""
    return (
        f"$primary: {resolve(theme.primary)};\n"
        f"$secondary: {resolve(theme.secondary)};\n"
        f"$accent: {resolve(theme.accent)};\n"
        f"$muted: {resolve(theme.muted)};\n"
        f"$error: {resolve(theme.error)};\n"
        f"$warning: {resolve(theme.warning)};\n"
        f"$success: {resolve(theme.success)};\n"
    )
