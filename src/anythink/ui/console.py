"""Rich Console factory for Anythink."""

from __future__ import annotations

from typing import IO

from rich.console import Console
from rich.theme import Theme as RichTheme

from anythink.ui.theme import Theme


def make_console(theme: Theme, file: IO[str] | None = None) -> Console:
    """Create a Rich Console wired to the given Anythink theme."""
    rich_theme = RichTheme(
        {
            "anythink.primary": theme.primary,
            "anythink.secondary": theme.secondary,
            "anythink.accent": theme.accent,
            "anythink.muted": theme.muted,
            "anythink.error": theme.error,
            "anythink.warning": theme.warning,
            "anythink.success": theme.success,
        }
    )
    return Console(
        file=file,
        theme=rich_theme,
        highlight=True,
        markup=True,
    )
