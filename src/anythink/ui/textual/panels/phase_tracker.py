"""Live plan execution phase tracker — replaces ThinkingWidget during Plan Mode (V4)."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from anythink.optimize.plan import PHASE_STATUS_DONE, PHASE_STATUS_FAILED, PHASE_STATUS_SKIPPED

if TYPE_CHECKING:
    from anythink.optimize.plan import ExecutionPlan, PhaseUpdate
    from anythink.ui.theme import Theme

_ICONS = {
    "waiting": "○",
    "running": "●",
    "queued": "⏳",
    "done": "✓",
    "failed": "✗",
    "skipped": "—",
}


class PhaseTrackerPanel(Widget):
    """Live plan execution tracker.

    Updated from a background worker via call_from_thread(update_phase, update).
    """

    can_focus = True

    DEFAULT_CSS = """
    PhaseTrackerPanel {
        height: auto;
        max-height: 24;
        border: solid $accent;
        background: $surface;
        display: none;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("p", "pause", "Pause", show=True),
        Binding("s", "skip", "Skip Phase", show=True),
        Binding("ctrl+c", "abort", "Abort", show=True),
    ]

    class PauseRequested(Message):
        """Posted when the user requests a pause after the current phase."""

    class SkipRequested(Message):
        """Posted when the user requests skipping the current phase."""

        def __init__(self, phase_num: int) -> None:
            super().__init__()
            self.phase_num = phase_num

    class AbortRequested(Message):
        """Posted when the user aborts execution."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._plan: ExecutionPlan | None = None
        self._theme: Theme | None = None
        self._current_phase: int = 0
        self._elapsed: float = 0.0

    def set_plan(self, plan: ExecutionPlan, theme: Theme) -> None:
        """Called from main thread before execution begins."""
        self._plan = plan
        self._theme = theme
        self._current_phase = 0
        self.display = True
        self._render()
        self.focus()

    def update_phase(self, update: PhaseUpdate) -> None:
        """Called via call_from_thread() from the plan runner worker."""
        if self._plan is None:
            return

        for phase in self._plan.phases:
            if phase.phase_num == update.phase_num:
                phase.status = update.status
                if update.actual_model:
                    phase.actual_model = update.actual_model
                phase.elapsed_s = update.elapsed_s
                break

        self._current_phase = update.phase_num
        self._elapsed = update.elapsed_s
        self._render()

    def compose(self) -> ComposeResult:
        yield Static("[b]Plan Mode — Executing[/b]", id="pt-header")
        yield Static("", id="pt-body")
        yield Static("  [p] Pause   [s] Skip   [Ctrl+C] Abort", id="pt-footer")

    def action_pause(self) -> None:
        self.post_message(self.PauseRequested())

    def action_skip(self) -> None:
        self.post_message(self.SkipRequested(self._current_phase))

    def action_abort(self) -> None:
        self.post_message(self.AbortRequested())

    def _render(self) -> None:
        if self._plan is None:
            return

        plan = self._plan
        lines: list[str] = [
            f"  Query: {plan.original_query[:60]}{'…' if len(plan.original_query) > 60 else ''}",
            "",
        ]

        terminal_statuses = (PHASE_STATUS_DONE, PHASE_STATUS_FAILED, PHASE_STATUS_SKIPPED)
        done_count = sum(1 for p in plan.phases if p.status in terminal_statuses)

        for phase in plan.phases:
            icon = _ICONS.get(phase.status, "○")
            model = phase.actual_model or phase.model_id
            elapsed = f"[{phase.elapsed_s:.1f}s]" if phase.elapsed_s > 0 else ""
            line = f"  {icon}  Phase {phase.phase_num} · {phase.title:<28} {model:<22} {elapsed}"
            lines.append(line)

        lines.append("")
        lines.append("  ○  Recombination")
        lines.append("")

        # Progress bar
        total = len(plan.phases)
        bar_filled = "█" * done_count
        bar_empty = "░" * (total - done_count)
        lines.append(f"  Progress: {bar_filled}{bar_empty}  {done_count}/{total} phases complete")

        with contextlib.suppress(Exception):
            self.query_one("#pt-body", Static).update("\n".join(lines))
