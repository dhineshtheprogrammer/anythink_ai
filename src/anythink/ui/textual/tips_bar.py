"""Rotating educational tips bar shown above the input while AI is generating."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import Static

from anythink.ui.icons import get_icon
from anythink.ui.theme import Theme

if TYPE_CHECKING:
    from textual.timer import Timer

    from anythink.config.schema import AppConfig

_TIPS = [
    "Use /model to switch between your saved models.",
    "Press Ctrl+Y to copy the last response to your clipboard.",
    "Use /branch to explore an alternate path without losing your conversation.",
    "Type /rag use <name> to load a saved knowledge index.",
    "Press Esc while a response is generating to stop it early.",
    "Use /bookmark to save important responses for later.",
    "Try /persona to give the AI a custom role for this session.",
    "Press Up/Down arrows to recall your previous messages.",
    "Use /settings to change your theme and default behaviours.",
    "Type /search <query> for a quick one-off web search.",
    "Press Ctrl+K to copy just the last code block to clipboard.",
    "Press Ctrl+O to open the full session file in your text editor.",
]


class TipsBar(Static):
    """Single rotating tip line shown during AI response generation."""

    DEFAULT_CSS = """
    TipsBar {
        height: 1;
        padding: 0 1;
        display: none;
    }
    """

    def __init__(self, theme: Theme, **kwargs: object) -> None:
        super().__init__("", **kwargs)  # type: ignore[arg-type]
        self._theme = theme
        self._config: AppConfig | None = None
        self._tip_idx = 0
        self._timer: Timer | None = None
        self._shuffled: list[str] = []

    # ── public API ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Reveal the bar and begin tip rotation."""
        self._shuffled = list(_TIPS)
        random.shuffle(self._shuffled)
        self._tip_idx = 0
        self._update_tip()
        self.display = True
        self._timer = self.set_interval(3.0, self._rotate_tip)

    def stop(self) -> None:
        """Hide the bar and stop rotation."""
        self.display = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    # ── internals ─────────────────────────────────────────────────────────

    def _rotate_tip(self) -> None:
        if not self._shuffled:
            return
        self._tip_idx = (self._tip_idx + 1) % len(self._shuffled)
        self._update_tip()

    def set_config(self, config: AppConfig) -> None:
        """Update the active config (for icon style changes)."""
        self._config = config

    def _update_tip(self) -> None:
        if not self._shuffled:
            return
        t = self._theme
        icon = get_icon("tip", self._config)
        line = Text()
        line.append(f"{icon} Tip: ", style=t.accent)
        line.append(self._shuffled[self._tip_idx], style=t.muted)
        self.update(line)
