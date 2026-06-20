"""Bottom-tab panel: RAG index browser with activate/deactivate controls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from anythink.app.context import AppContext


class RAGBrowserTab(Widget):
    """Tab pane that lists RAG indexes and lets the user activate one."""

    DEFAULT_CSS = """
    RAGBrowserTab {
        height: 1fr;
        padding: 0 1;
    }
    """

    class IndexActivated(Message):
        """Posted when the user requests activating a named index."""

        def __init__(self, index_name: str) -> None:
            super().__init__()
            self.index_name = index_name

    def __init__(self, ctx: AppContext, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._ctx = ctx

    def compose(self) -> ComposeResult:
        yield Static("", id="rag-listing")

    def on_mount(self) -> None:
        self.refresh_index_list()

    def refresh_index_list(self) -> None:
        """Re-render the index list from RAGManager state."""
        rm = self._ctx.rag_manager
        try:
            indexes = rm.list_indexes()
        except Exception:
            indexes = []

        if not indexes:
            text = (
                "[dim]No RAG indexes defined.[/dim]\n\n" "Use [b]/rag new <name>[/b] to create one."
            )
            self.query_one("#rag-listing", Static).update(text)
            return

        lines = [f"  {'Name':<20} {'Chunks':<8} Status"]
        lines.append("  " + "─" * 38)
        for idx in indexes:
            active = " ← active" if rm.active_name == idx.name else ""
            last = idx.last_indexed.strftime("%Y-%m-%d") if idx.last_indexed else "never"
            lines.append(f"  {idx.name:<20} {idx.chunk_count:<8} {last}{active}")
        lines.append("")
        lines.append("[dim]Use /rag use <name> to activate.[/dim]")
        self.query_one("#rag-listing", Static).update("\n".join(lines))
