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


def theme_css_vars(theme: Theme) -> dict[str, str]:
    """Return CSS variable values for all theme tokens.

    The returned dict maps variable names (without ``$``) to CSS color strings.
    Pass to Textual's ``get_css_variables()`` override.
    """
    return {
        "primary": resolve(theme.primary),
        "secondary": resolve(theme.secondary),
        "accent": resolve(theme.accent),
        "muted": resolve(theme.muted),
        "error": resolve(theme.error),
        "warning": resolve(theme.warning),
        "success": resolve(theme.success),
        "info": resolve(theme.info),
        # background and surface are already hex strings
        "background": theme.background,
        "surface": theme.surface,
        "panel": theme.surface,
    }
