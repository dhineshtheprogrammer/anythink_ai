"""Theme definitions for the Anythink terminal UI."""

from __future__ import annotations

from dataclasses import dataclass, field

from anythink.exceptions import ConfigError


@dataclass(frozen=True)
class Theme:
    """Color palette for the terminal UI."""

    name: str
    primary: str  # main assistant-response text / user bubble borders
    secondary: str  # subtext, metadata, tagline
    accent: str  # AI bubble borders, headers, highlights
    muted: str  # dimmed / placeholder text / muted borders
    error: str  # error messages
    warning: str  # warning / orange-zone context bar
    success: str  # success messages, green-zone context bar
    info: str  # info / neutral semantic color
    background: str  # full-screen canvas tint (CSS hex, e.g. "#0a0a12")
    surface: str  # slightly lifted bubble/panel surface (CSS hex)
    logo: str | None = field(default=None)  # logo color override; None → falls back to primary
    is_light_bg: bool = field(default=False)  # True → Linen-style dark HUD bar treatment


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

CHARCOAL = Theme(
    name="charcoal",
    primary="#9EAAB5",
    secondary="#5C9CF5",
    accent="#5C9CF5",
    muted="#6E6E6E",
    error="#E06C75",
    warning="#D4A847",
    success="#6ABF69",
    info="#7DB3E8",
    background="#1E1E1E",
    surface="#252525",
    logo="#5C9CF5",
)

LINEN = Theme(
    name="linen",
    primary="#1E3A5F",
    secondary="#0F6B6B",
    accent="#0F6B6B",
    muted="#8A8680",
    error="#991B1B",
    warning="#92400E",
    success="#166534",
    info="#1E40AF",
    background="#F4F1EB",
    surface="#EBE8E0",
    is_light_bg=True,
)

ROSE = Theme(
    name="rose",
    primary="#E8A0B4",
    secondary="#FF79A8",
    accent="#FF79A8",
    muted="#8A6070",
    error="#FF4D6D",
    warning="#F4C77A",
    success="#7DC4A8",
    info="#C084FC",
    background="#1A0E12",
    surface="#231318",
)

DRACULA = Theme(
    name="dracula",
    primary="#BD93F9",
    secondary="#FF79C6",
    accent="#FF79C6",
    muted="#6272A4",
    error="#FF5555",
    warning="#F1FA8C",
    success="#50FA7B",
    info="#8BE9FD",
    background="#282A36",
    surface="#44475A",
)

THEMES: dict[str, Theme] = {
    t.name: t for t in (MIDNIGHT, AURORA, EMBER, ARCTIC, CHARCOAL, LINEN, ROSE, DRACULA)
}


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
