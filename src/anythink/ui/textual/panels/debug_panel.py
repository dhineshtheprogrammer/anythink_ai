"""Live debug side panel widget for V3.2.0 debug infrastructure."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from anythink.debug.models import RequestDebugRecord


class DebugPanel(Widget):
    """Right-side panel that streams debug events in real time."""

    DEFAULT_CSS = """
    DebugPanel {
        width: 32;
        display: none;
        border-left: tall #444444;
        padding: 0 1;
        overflow-y: auto;
    }
    DebugPanel #dp-header {
        text-style: bold;
        color: $accent;
        padding: 0 0 1 0;
    }
    DebugPanel .dp-divider {
        color: $primary;
        text-style: bold;
    }
    DebugPanel .dp-event {
        color: $muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[b]🔬 Debug Panel[/b]", id="dp-header")
        yield VerticalScroll(
            Static("[dim]No events yet.[/dim]", id="dp-placeholder"),
            id="dp-log",
        )

    # ── public API ────────────────────────────────────────────────────────

    def set_level(self, level: int) -> None:
        """Update panel header to reflect the current verbosity level."""
        import contextlib

        with contextlib.suppress(Exception):
            self.query_one("#dp-header", Static).update(f"[b]🔬 Debug Panel · L{level}[/b]")

    async def begin_request(self, request_id: int, ts: str) -> None:
        """Start a new request section with a labelled divider."""
        await self._clear_placeholder()
        await self._append_line(
            f"── Request #{request_id} · {ts} ──",
            classes="dp-divider",
        )

    async def append_event(self, label: str, detail: str = "") -> None:
        """Add one event line to the live event log."""
        text = f"▸ {label}"
        if detail:
            text += f"  {detail}"
        await self._append_line(text, classes="dp-event")

    async def finalize_request(self, record: RequestDebugRecord, level: int) -> None:
        """Append a summary row when a request completes."""
        parts: list[str] = []
        if record.ttft_ms() is not None:
            parts.append(f"TTFT {record.ttft_ms():.0f}ms")
        tw = record.total_wall_ms()
        if tw:
            parts.append(f"Total {tw:.0f}ms")
        if record.stop_reason:
            parts.append(f"stop: {record.stop_reason}")
        if record.tokens_per_second:
            parts.append(f"{record.tokens_per_second:.0f} tok/s")
        if level >= 2 and record.completion_tokens:
            parts.append(f"{record.completion_tokens} tokens")
        summary = "  ".join(parts) if parts else "done"
        await self._append_line(f"  ✓ {summary}", classes="dp-event")

    # ── internals ─────────────────────────────────────────────────────────

    async def _clear_placeholder(self) -> None:
        import contextlib

        with contextlib.suppress(Exception):
            ph = self.query_one("#dp-placeholder")
            await ph.remove()

    async def _append_line(self, text: str, *, classes: str = "") -> None:
        import contextlib

        with contextlib.suppress(Exception):
            log = self.query_one("#dp-log", VerticalScroll)
            await log.mount(Static(text, classes=classes))
            log.scroll_end(animate=False)
