"""Persistent shortcut hint bar displayed below the input area."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from anythink.ui.theme import Theme

_HINTS_DEFAULT = [
    ("Ctrl+Y", "copy response"),
    ("Ctrl+K", "copy code"),
    ("Ctrl+O", "open in editor"),
    ("Esc", "stop"),
    ("/", "commands"),
]

_HINTS_STREAMING = [
    ("Esc", "stop generation"),
    ("Ctrl+Y", "copy partial"),
    ("/", "commands"),
]


class HintBar(Static):
    """Single-line shortcut reference bar, always visible below the input."""

    DEFAULT_CSS = """
    HintBar {
        height: 1;
        dock: bottom;
        padding: 0 1;
    }
    """

    def __init__(self, theme: Theme, **kwargs: object) -> None:
        super().__init__("", **kwargs)  # type: ignore[arg-type]
        self._theme = theme
        self._streaming = False

    # ── public API ─────────────────────────────────────────────────────────

    def set_streaming(self, active: bool) -> None:
        """Switch between streaming and resting hint sets."""
        self._streaming = active
        self._refresh_hints()

    # ── lifecycle ──────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._refresh_hints()

    # ── rendering ─────────────────────────────────────────────────────────

    def _refresh_hints(self) -> None:
        t = self._theme
        hints = _HINTS_STREAMING if self._streaming else _HINTS_DEFAULT
        line = Text()
        sep = Text("  │  ", style=t.muted)
        for i, (key, label) in enumerate(hints):
            if i:
                line.append_text(sep)
            key_style = t.accent if (self._streaming and key == "Esc") else t.secondary
            line.append(key, style=key_style)
            line.append(f" {label}", style=t.muted)
        self.update(line)
