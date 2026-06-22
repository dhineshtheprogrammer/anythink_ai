"""Theme definitions for the Anythink terminal UI."""

from __future__ import annotations

from dataclasses import dataclass

from anythink.exceptions import ConfigError


@dataclass(frozen=True)
class Theme:
    """Color palette for the terminal UI."""

    name: str
    primary: str  # main assistant-response text
    secondary: str  # subtext, metadata
    accent: str  # headers, highlights
    muted: str  # dimmed / placeholder text
    error: str  # error messages
    warning: str  # warning / orange-zone context bar
    success: str  # success messages, green-zone context bar
    info: str  # info / neutral semantic color
    background: str  # full-screen canvas tint (CSS hex, e.g. "#0a0a12")
    surface: str  # slightly lifted bubble/panel surface (CSS hex)


MIDNIGHT = Theme(
    name="midnight",
    primary="bright_cyan",
    secondary="cyan",
    accent="bright_blue",
    muted="grey58",
    error="bright_red",
    warning="bright_yellow",
    success="bright_green",
    info="bright_cyan",
    background="#0a0a12",
    surface="#10101c",
)

AURORA = Theme(
    name="aurora",
    primary="bright_magenta",
    secondary="magenta",
    accent="bright_cyan",
    muted="grey54",
    error="bright_red",
    warning="bright_yellow",
    success="bright_green",
    info="bright_green",
    background="#080f08",
    surface="#0e160e",
)

EMBER = Theme(
    name="ember",
    primary="bright_yellow",
    secondary="yellow",
    accent="bright_red",
    muted="grey46",
    error="red",
    warning="dark_orange",
    success="green",
    info="dark_orange",
    background="#120a06",
    surface="#1c100a",
)

ARCTIC = Theme(
    name="arctic",
    primary="white",
    secondary="bright_white",
    accent="bright_cyan",
    muted="grey70",
    error="bright_red",
    warning="bright_yellow",
    success="bright_green",
    info="cyan",
    background="#080c12",
    surface="#0e1218",
)

THEMES: dict[str, Theme] = {t.name: t for t in (MIDNIGHT, AURORA, EMBER, ARCTIC)}


def get_theme(name: str) -> Theme:
    """Return a Theme by name, raising ConfigError for unknown names."""
    try:
        return THEMES[name]
    except KeyError:
        valid = ", ".join(sorted(THEMES))
        raise ConfigError(
            message=f"Unknown theme: {name!r}. Valid themes: {valid}",
            user_message=f"Unknown theme '{name}'. Choose from: {valid}",
        ) from None
