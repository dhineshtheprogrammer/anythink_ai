"""ASCII art banner for the Anythink CLI."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from anythink.ui.theme import Theme

_BANNER = r"""
  __ _ _ __  _   _| |_| |__ (_)_ __ | | __
 / _` | '_ \| | | | __| '_ \| | '_ \| |/ /
| (_| | | | | |_| | |_| | | | | | | |   <
 \__,_|_| |_|\__, |\__|_| |_|_|_| |_|_|\_\
             |___/
"""


def print_banner(console: Console, theme: Theme, version: str) -> None:
    """Print the Anythink ASCII banner with version and tagline."""
    console.print(Text(_BANNER, style=theme.logo or theme.primary))
    console.print(
        Text(
            f"  Think anything. Ask anything.  •  v{version}",
            style=theme.secondary,
        )
    )
    console.print()
