"""Input area widget anchored to the bottom of the chat screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input

from anythink.ui.textual.slash_menu import SlashMenu

if TYPE_CHECKING:
    from anythink.commands.base import SlashCommand
    from anythink.ui.theme import Theme


class InputArea(Widget):
    """Single-line input widget that posts ``InputArea.Submitted`` on Enter.

    The widget clears automatically after each submission so the user's
    focus and caret are always ready for the next message.

    Up/Down arrow keys navigate the current-session message history, unless
    the slash-command drop-up menu is open (where they navigate the menu).
    """

    DEFAULT_CSS = """
    InputArea {
        height: auto;
        padding: 0 1;
    }
    InputArea > Input {
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("up", "navigate_up", show=False, priority=True),
        Binding("down", "navigate_down", show=False, priority=True),
        Binding("tab", "select_command", show=False, priority=True),
        Binding("escape", "dismiss_menu", show=False, priority=True),
    ]

    class Submitted(Message):
        """Posted when the user submits a message (Enter key)."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._sent_history: list[str] = []
        self._history_idx: int = -1
        self._slash_commands: list[SlashCommand] = []
        self._theme: Theme | None = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Type a message… (/help for commands)")

    # ── public API ─────────────────────────────────────────────────────────

    def configure(self, commands: list[SlashCommand], theme: Theme) -> None:
        """Wire up the slash command list and theme (called from app after mount)."""
        self._slash_commands = commands
        self._theme = theme
        try:
            self.query_one(SlashMenu)
        except Exception:
            if self._theme is not None:
                self.mount(SlashMenu(self._theme, id="slash-menu"))

    # ── input submission ───────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Intercept Enter in the inner Input, clear it, and bubble up.

        If the slash menu is open, select the highlighted entry instead of submitting.
        Empty submissions are forwarded so the app can handle interactive
        modes (e.g. session naming, undo confirmation) where Enter = confirm.
        """
        menu = self._get_menu()
        if menu is not None and menu.is_open():
            menu.select_current()
            event.stop()
            return

        text = event.value.strip()
        if text:
            self._sent_history.append(text)
            self._history_idx = -1
        event.input.clear()
        self.post_message(self.Submitted(text))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Live-filter slash menu as the user types."""
        value = event.value
        menu = self._get_menu()
        if menu is None:
            return
        if value.startswith("/"):
            menu.show(self._slash_commands, value)
        else:
            menu.hide()

    def on_slash_menu_selected(self, event: SlashMenu.Selected) -> None:
        """Insert the selected command name into the input."""
        inp = self.query_one(Input)
        inp.value = f"/{event.command_name} "
        inp.cursor_position = len(inp.value)
        inp.focus()

    # ── navigation actions ─────────────────────────────────────────────────

    def action_navigate_up(self) -> None:
        menu = self._get_menu()
        if menu is not None and menu.is_open():
            menu.move_up()
        else:
            self._history_prev()

    def action_navigate_down(self) -> None:
        menu = self._get_menu()
        if menu is not None and menu.is_open():
            menu.move_down()
        else:
            self._history_next()

    def action_select_command(self) -> None:
        """Tab: select the highlighted menu item."""
        menu = self._get_menu()
        if menu is not None and menu.is_open():
            menu.select_current()

    def action_dismiss_menu(self) -> None:
        """Escape: close the slash menu if open; otherwise pass to app bindings."""
        menu = self._get_menu()
        if menu is not None and menu.is_open():
            menu.hide()

    # ── history navigation ─────────────────────────────────────────────────

    def _history_prev(self) -> None:
        """Recall an older sent message."""
        if not self._sent_history:
            return
        self._history_idx = min(self._history_idx + 1, len(self._sent_history) - 1)
        inp = self.query_one(Input)
        inp.value = self._sent_history[-(self._history_idx + 1)]
        inp.cursor_position = len(inp.value)

    def _history_next(self) -> None:
        """Advance toward the most recent message; blank on overshoot."""
        inp = self.query_one(Input)
        self._history_idx -= 1
        if self._history_idx < 0:
            self._history_idx = -1
            inp.value = ""
        else:
            inp.value = self._sent_history[-(self._history_idx + 1)]
            inp.cursor_position = len(inp.value)

    # ── helpers ────────────────────────────────────────────────────────────

    def _get_menu(self) -> SlashMenu | None:
        try:
            return self.query_one(SlashMenu)
        except Exception:
            return None
