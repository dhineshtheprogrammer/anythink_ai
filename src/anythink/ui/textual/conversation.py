"""Scrollable conversation view that holds chat bubbles."""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widget import Widget


class ConversationView(VerticalScroll):
    """Scrollable container for UserBubble, AIBubble, and SystemBubble widgets."""

    DEFAULT_CSS = """
    ConversationView {
        height: 1fr;
        padding: 1 2;
    }
    """

    def add_bubble(self, bubble: Widget) -> None:
        """Mount *bubble* and immediately scroll to the bottom."""
        self.mount(bubble)
        self.scroll_end(animate=False)
