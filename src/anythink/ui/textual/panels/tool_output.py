"""Bottom-tab panel: aggregated log of all Phase-5/6 tool call results."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static


class ToolOutputTab(Widget):
    """Tab pane that accumulates tool execution events across the session."""

    DEFAULT_CSS = """
    ToolOutputTab {
        height: 1fr;
        padding: 0 1;
    }
    ToolOutputTab VerticalScroll {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Static("[dim]No tool calls yet.[/dim]", id="tool-log-placeholder"),
            id="tool-log",
        )
        self._event_count = 0

    def add_event(self, tool_name: str, server_or_kind: str, summary: str) -> None:
        """Append a tool-call event entry."""
        scroll = self.query_one("#tool-log", VerticalScroll)

        # Remove placeholder on first real event
        if self._event_count == 0:
            import contextlib

            with contextlib.suppress(Exception):
                scroll.query_one("#tool-log-placeholder").remove()

        ts = datetime.now().strftime("%H:%M:%S")
        header = f"[dim]{ts}[/dim] [b]{tool_name}[/b] [{server_or_kind}]"
        body = summary[:200] + ("…" if len(summary) > 200 else "")
        scroll.mount(Static(f"{header}\n{body}\n"))
        scroll.scroll_end(animate=False)
        self._event_count += 1
