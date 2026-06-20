"""Left dashboard panel: scrollable session list with active-session marker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, Static

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.session.models import Session


class SessionListPanel(Widget):
    """Left panel listing saved sessions; posts ``SessionSelected`` on click."""

    DEFAULT_CSS = """
    SessionListPanel {
        width: 24;
        display: none;
        border-right: tall #767676;
        padding: 0;
    }
    SessionListPanel .panel-header {
        height: 1;
        padding: 0 1;
        background: #1a1a1a;
    }
    """

    class SessionSelected(Message):
        """Posted when the user clicks a session in the list."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    def __init__(self, ctx: AppContext, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._ctx = ctx
        self._sessions: list[Session] = []

    def compose(self) -> ComposeResult:
        yield Static("[b] Sessions[/b]", classes="panel-header")
        yield ListView(id="session-list")

    def on_mount(self) -> None:
        self.refresh_sessions("")

    def refresh_sessions(self, active_id: str) -> None:
        """Reload the session list, highlighting *active_id* if given."""
        lv = self.query_one(ListView)
        lv.clear()
        try:
            self._sessions = self._ctx.session_manager.list_sessions()
        except Exception:
            self._sessions = []

        for s in self._sessions:
            name = s.name or s.id[:8] + "…"
            ts = s.updated_at.strftime("%m-%d %H:%M") if hasattr(s, "updated_at") else ""
            marker = "●" if s.id == active_id else " "
            label = f"{marker} {name}"
            if ts:
                label += f"\n  [dim]{ts}[/dim]"
            lv.append(ListItem(Label(label)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Map the list selection back to a session ID and post the message."""
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._sessions):
            self.post_message(self.SessionSelected(self._sessions[idx].id))
