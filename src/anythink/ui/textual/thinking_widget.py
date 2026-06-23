"""Animated loading indicator shown while the AI is generating a response."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import Static

from anythink.ui.icons import get_spinner_frames
from anythink.ui.theme import Theme

if TYPE_CHECKING:
    from textual.timer import Timer

_GENERIC_PHRASES = [
    "Thinking…",
    "Pondering…",
    "Drafting a response…",
    "Connecting the dots…",
    "Mulling it over…",
    "Reasoning it through…",
    "Composing thoughts…",
    "Gathering ideas…",
    "Working it out…",
    "Sketching a reply…",
    "Putting it together…",
    "Considering the angles…",
]


class ThinkingWidget(Static):
    """Animated spinner + contextual phrase shown during AI generation.

    Mounts into the ConversationView just before the AIBubble.
    Disappears automatically when ``stop()`` is called.
    """

    DEFAULT_CSS = """
    ThinkingWidget {
        margin: 0 8 0 8;
        height: 1;
    }
    """

    def __init__(self, theme: Theme, **kwargs: object) -> None:
        super().__init__("", **kwargs)  # type: ignore[arg-type]
        self._theme = theme
        self._frame = 0
        self._phrase_idx = 0
        self._context_phrase: str | None = None
        self._active = False
        self._frames: list[str] = get_spinner_frames(None)
        self._spin_timer: Timer | None = None
        self._phrase_timer: Timer | None = None

    # ── public API ─────────────────────────────────────────────────────────

    def set_context(self, phrase: str | None) -> None:
        """Override the rotating phrase pool with a specific contextual phrase.

        Pass ``None`` to return to random rotation.
        """
        self._context_phrase = phrase
        self._refresh_display()

    def stop(self) -> None:
        """Stop animation timers and hide the widget."""
        self._active = False
        if self._spin_timer is not None:
            self._spin_timer.stop()
        if self._phrase_timer is not None:
            self._phrase_timer.stop()
        self.display = False

    # ── lifecycle ──────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._active = True
        phrases = list(_GENERIC_PHRASES)
        random.shuffle(phrases)
        self._spin_timer = self.set_interval(0.3, self._advance_spinner)
        self._phrase_timer = self.set_interval(1.8, self._advance_phrase)
        self._refresh_display()

    # ── internals ─────────────────────────────────────────────────────────

    def _advance_spinner(self) -> None:
        if not self._active:
            return
        self._frame = (self._frame + 1) % len(self._frames)
        self._refresh_display()

    def _advance_phrase(self) -> None:
        if not self._active or self._context_phrase is not None:
            return
        self._phrase_idx = (self._phrase_idx + 1) % len(_GENERIC_PHRASES)
        self._refresh_display()

    def _refresh_display(self) -> None:
        t = self._theme
        phrase = self._context_phrase or _GENERIC_PHRASES[self._phrase_idx]
        spinner = self._frames[self._frame]
        line = Text()
        line.append(f" {spinner} ", style=t.accent)
        line.append(phrase, style=t.muted)
        self.update(line)
