"""Drop-up autocomplete menu for slash commands, shown above the input box."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from anythink.commands.base import SlashCommand
    from anythink.ui.theme import Theme


class _MenuRow(Static):
    """A single row in the slash-command drop-up."""

    DEFAULT_CSS = """
    _MenuRow {
        height: 1;
        padding: 0 1;
    }
    _MenuRow.highlighted {
        background: $accent 20%;
    }
    """

    def __init__(self, name: str, description: str, theme: Theme) -> None:
        super().__init__("")
        self._name = name
        self._description = description
        self._theme = theme
        self._highlighted = False

    def set_highlighted(self, value: bool) -> None:
        self._highlighted = value
        self._refresh_row()
        if value:
            self.add_class("highlighted")
        else:
            self.remove_class("highlighted")

    def on_mount(self) -> None:
        self._refresh_row()

    def _refresh_row(self) -> None:
        t = self._theme
        line = Text()
        name_style = t.accent if self._highlighted else t.secondary
        line.append(f"/{self._name:<16}", style=name_style)
        line.append(f"  {self._description}", style=t.muted)
        self.update(line)


class SlashMenu(Widget):
    """Drop-up command completion menu.

    Appears above the input when the user types '/'.  Navigation via
    Up/Down arrows; Tab/Enter selects; Escape dismisses.
    """

    DEFAULT_CSS = """
    SlashMenu {
        height: auto;
        max-height: 10;
        border: solid $accent;
        background: $surface;
        display: none;
    }
    """

    class Selected(Message):
        """Posted when a command is chosen from the menu."""

        def __init__(self, command_name: str) -> None:
            super().__init__()
            self.command_name = command_name

    def __init__(self, theme: Theme, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._theme = theme
        self._commands: list[SlashCommand] = []
        self._filtered: list[SlashCommand] = []
        self._index: int = 0

    # ── public API ─────────────────────────────────────────────────────────

    def is_open(self) -> bool:
        return self.display

    def show(self, commands: list[SlashCommand], text: str) -> None:
        """Filter and display matching commands for *text* (including leading '/')."""
        query = text.lstrip("/").lower()
        self._commands = commands
        if query:
            self._filtered = [c for c in commands if c.name.startswith(query)]
        else:
            self._filtered = list(commands)
        self._index = 0
        self._rebuild()
        self.display = bool(self._filtered)

    def hide(self) -> None:
        self.display = False

    def move_up(self) -> None:
        if not self._filtered:
            return
        self._index = (self._index - 1) % len(self._filtered)
        self._update_highlight()

    def move_down(self) -> None:
        if not self._filtered:
            return
        self._index = (self._index + 1) % len(self._filtered)
        self._update_highlight()

    def select_current(self) -> None:
        if self._filtered:
            self.post_message(self.Selected(self._filtered[self._index].name))
            self.hide()

    # ── internals ─────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        return iter([])  # rows mounted dynamically in _rebuild

    def _rebuild(self) -> None:
        """Remove all rows and remount matching commands."""
        for child in list(self.children):
            child.remove()
        for i, cmd in enumerate(self._filtered):
            row = _MenuRow(cmd.name, cmd.description, self._theme)
            if i == self._index:
                row.set_highlighted(True)
            self.mount(row)

    def _update_highlight(self) -> None:
        rows = list(self.query(_MenuRow))
        for i, row in enumerate(rows):
            row.set_highlighted(i == self._index)
