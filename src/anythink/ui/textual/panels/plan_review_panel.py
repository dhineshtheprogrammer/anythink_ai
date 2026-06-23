"""Plan review panel — shows generated plan for user approval before execution (V4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from anythink.optimize.plan import ExecutionPlan
    from anythink.ui.theme import Theme


class PlanReviewPanel(Widget):
    """Full-screen plan review overlay.

    Shows all phases with model assignments and token estimates.
    User can approve, reject, request regeneration, or enter edit mode.
    """

    can_focus = True

    DEFAULT_CSS = """
    PlanReviewPanel {
        height: auto;
        max-height: 40;
        border: solid $accent;
        background: $surface;
        display: none;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("a", "approve", "Approve & Run", show=True),
        Binding("r", "reject", "Reject", show=True),
        Binding("g", "regenerate", "Re-generate", show=True),
        Binding("escape", "reject", show=False, priority=True),
    ]

    class Approved(Message):
        """Posted when the user approves the plan."""

    class Rejected(Message):
        """Posted when the user rejects the plan."""

    class Regenerate(Message):
        """Posted when the user requests a new plan generation."""

    class EditRequested(Message):
        """Posted when the user wants to edit the plan inline."""

        def __init__(self, plan: ExecutionPlan) -> None:
            super().__init__()
            self.plan = plan

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._plan: ExecutionPlan | None = None
        self._theme: Theme | None = None

    def show_plan(self, plan: ExecutionPlan, theme: Theme) -> None:
        self._plan = plan
        self._theme = theme
        self.display = True
        self._render_plan()
        self.focus()

    def compose(self) -> ComposeResult:
        yield Static("[b]Plan Mode — Review Plan[/b]", id="pr-header")
        yield Static("", id="pr-body")
        yield Static(
            "  [a] Approve & Run   [g] Re-generate   [Esc/r] Reject",
            id="pr-footer",
        )

    def action_approve(self) -> None:
        self.display = False
        self.post_message(self.Approved())

    def action_reject(self) -> None:
        self.display = False
        self.post_message(self.Rejected())

    def action_regenerate(self) -> None:
        self.display = False
        self.post_message(self.Regenerate())

    def _render_plan(self) -> None:
        import contextlib

        if self._plan is None:
            return

        plan = self._plan
        lines: list[str] = [
            f"  Query: {plan.original_query[:70]}{'…' if len(plan.original_query) > 70 else ''}",
            "  " + "─" * 70,
        ]

        for phase in plan.phases:
            dep_str = (
                f"  (depends on: {', '.join(str(d) for d in phase.depends_on)})"
                if phase.depends_on
                else ""
            )
            detail = (
                f"    Model: {phase.model_id}"
                f"  ·  Est. tokens: ~{phase.estimated_tokens:,}"
                f"  ·  Type: {phase.output_type}{dep_str}"
            )
            lines += [
                f"  Phase {phase.phase_num} of {len(plan.phases)}: {phase.title}",
                detail,
                f"    {phase.description}",
                "",
            ]

        min_m, max_m = plan.estimated_minutes
        lines += [
            "  " + "─" * 70,
            f"  Total est. tokens: ~{plan.total_estimated_tokens:,}  ·  "
            f"Models: {len(plan.unique_models)}  ·  Phases: {len(plan.phases)}",
            f"  Estimated time: ~{min_m}–{max_m} minutes",
        ]

        with contextlib.suppress(Exception):
            self.query_one("#pr-body", Static).update("\n".join(lines))
