"""Input area widget anchored to the bottom of the chat screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input


class InputArea(Widget):
    """Single-line input widget that posts ``InputArea.Submitted`` on Enter.

    The widget clears automatically after each submission so the user's
    focus and caret are always ready for the next message.
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

    class Submitted(Message):
        """Posted when the user submits a message (Enter key)."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Type a message… (/help for commands)")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Intercept Enter in the inner Input, clear it, and bubble up.

        Empty submissions are forwarded so the app can handle interactive
        modes (e.g. session naming, undo confirmation) where Enter = confirm.
        """
        text = event.value.strip()
        event.input.clear()
        self.post_message(self.Submitted(text))
