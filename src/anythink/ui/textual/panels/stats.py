"""Right dashboard panel: model, context-window, and MCP/RAG stats."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from anythink.app.chat import ChatState
    from anythink.app.context import AppContext


class StatsPanel(Widget):
    """Right panel showing live model and session statistics."""

    DEFAULT_CSS = """
    StatsPanel {
        width: 28;
        display: none;
        border-left: tall #767676;
        padding: 0 1;
    }
    StatsPanel .panel-header {
        height: 1;
        background: #1a1a1a;
    }
    """

    def __init__(self, ctx: AppContext, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._ctx = ctx

    def compose(self) -> ComposeResult:
        yield Static("[b] Stats[/b]", classes="panel-header")
        yield Static("", id="stats-body")

    def update_stats(self, ctx: AppContext, state: ChatState | None) -> None:
        """Refresh the panel content from *ctx* and *state*."""
        lines: list[str] = []

        if state is not None:
            lines.append(f"Provider:  {state.provider.display_name}")
            lines.append(f"Model:     {state.model_id[:22]}")
            lines.append("")
            used = state.total_tokens_used
            total = state.context_window
            pct = (used / total * 100) if total > 0 else 0.0
            lines.append(f"Tokens:    {used:,}/{total:,}")
            lines.append(f"           ({pct:.0f}% used)")
            lines.append(f"History:   {len(state.history)} msg(s)")
            lines.append(f"Branch:    {state.active_branch}")
            if state.session_name:
                sname = state.session_name[:20]
                lines.append(f"Session:   {sname}")
        else:
            lines.append("[dim]No session active.[/dim]")

        lines.append("")
        lines.append("─" * 22)
        lines.append("")

        # MCP
        servers = ctx.mcp_manager.list_servers()
        builtins = sum(1 for s in servers if s.kind == "builtin")
        externals = sum(1 for s in servers if s.kind == "external")
        lines.append(f"MCP:       {builtins} built-in")
        if externals:
            lines.append(f"           {externals} external")

        # RAG
        rm = ctx.rag_manager
        if rm.is_active and rm.active_name:
            info = rm.get_info(rm.active_name)
            chunk_str = f", {info.chunk_count:,} chunks" if info else ""
            lines.append(f"RAG:       {rm.active_name[:16]}{chunk_str}")
        else:
            lines.append("RAG:       [dim]inactive[/dim]")

        self.query_one("#stats-body", Static).update("\n".join(lines))
