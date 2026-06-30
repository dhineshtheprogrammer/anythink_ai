"""Live workflow side panel widget for the MMWE (Multi-Model Workflow Engine)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    pass


class WorkflowPanel(Widget):
    """Right-side panel that shows live MMWE workflow progress."""

    DEFAULT_CSS = """
    WorkflowPanel {
        width: 36;
        display: none;
        border-left: tall #444444;
        padding: 0 1;
        overflow-y: auto;
    }
    WorkflowPanel #wp-header {
        text-style: bold;
        color: $accent;
        padding: 0 0 1 0;
    }
    WorkflowPanel .wp-divider {
        color: $primary;
        text-style: bold;
    }
    WorkflowPanel .wp-stage-start {
        color: $accent;
    }
    WorkflowPanel .wp-stage-ok {
        color: $success;
    }
    WorkflowPanel .wp-stage-err {
        color: $error;
    }
    WorkflowPanel .wp-approval {
        color: $warning;
        text-style: bold;
    }
    WorkflowPanel .wp-done {
        color: $success;
        text-style: bold;
    }
    WorkflowPanel .wp-event {
        color: $muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[b]⚙ Workflow Panel[/b]", id="wp-header")
        yield VerticalScroll(
            Static("[dim]No workflow running.[/dim]", id="wp-placeholder"),
            id="wp-log",
        )

    # ── public API ────────────────────────────────────────────────────

    async def begin_workflow(self, name: str) -> None:
        """Show workflow name and clear previous log entries."""
        await self._clear_log()
        self.query_one("#wp-header", Static).update(f"[b]⚙ Workflow · {name}[/b]")
        await self._append_line(f"── {name} ──", classes="wp-divider")

    async def stage_started(self, stage_id: str, label: str) -> None:
        """Log that a stage has begun executing."""
        display = label or stage_id
        await self._append_line(f"▸ {display}", classes="wp-stage-start")

    async def stage_complete(self, stage_id: str, ok: bool, summary: str = "") -> None:
        """Log that a stage has completed."""
        cls = "wp-stage-ok" if ok else "wp-stage-err"
        icon = "✓" if ok else "✗"
        text = f"  {icon} {stage_id}"
        if summary:
            short = summary[:60].replace("\n", " ")
            text += f"  → {short}"
        await self._append_line(text, classes=cls)

    async def approval_needed(self, message: str) -> None:
        """Show an approval prompt inside the panel."""
        await self._append_line(f"⚠ {message}", classes="wp-approval")
        await self._append_line("  Type y / skip / abort in the chat input.", classes="wp-event")

    async def loop_progress(self, current: int, total: int) -> None:
        """Show iteration progress for LOOP stages."""
        await self._append_line(f"  ↻ {current}/{total}", classes="wp-event")

    async def workflow_done(self, status: str, final_output: str = "") -> None:
        """Show completion or failure banner."""
        icon = "✔" if status == "completed" else "✗"
        label = status.upper()
        await self._append_line(f"{icon} {label}", classes="wp-done")
        if final_output:
            short = final_output[:120].replace("\n", " ")
            await self._append_line(f"  {short}", classes="wp-event")
        self.query_one("#wp-header", Static).update("[b]⚙ Workflow Panel[/b]")

    async def clear(self) -> None:
        """Reset the panel to its initial empty state."""
        await self._clear_log()
        self.query_one("#wp-header", Static).update("[b]⚙ Workflow Panel[/b]")

    # ── internals ─────────────────────────────────────────────────────

    async def _clear_log(self) -> None:
        import contextlib

        log = self.query_one("#wp-log", VerticalScroll)
        children = list(log.children)
        for child in children:
            with contextlib.suppress(Exception):
                await child.remove()
        await log.mount(Static("[dim]Running…[/dim]", id="wp-placeholder"))

    async def _append_line(self, text: str, *, classes: str = "") -> None:
        import contextlib

        with contextlib.suppress(Exception):
            log = self.query_one("#wp-log", VerticalScroll)
            # Remove placeholder on first real entry
            with contextlib.suppress(Exception):
                ph = log.query_one("#wp-placeholder")
                await ph.remove()
            await log.mount(Static(text, classes=classes))
            log.scroll_end(animate=False)
