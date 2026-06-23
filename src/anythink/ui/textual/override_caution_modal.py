"""Override caution modal — warns when a user override conflicts with constraints (V4)."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from anythink.ui.theme import Theme


class OverrideCautionModal(Widget):
    """Inline caution modal shown when a user override conflicts with system constraints.

    Blocks the query until the user chooses to proceed, use the recommended model,
    or cancel entirely.
    """

    can_focus = True

    DEFAULT_CSS = """
    OverrideCautionModal {
        height: auto;
        max-height: 12;
        border: solid $warning;
        background: $surface;
        display: none;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("p", "proceed", "Proceed anyway", show=True),
        Binding("u", "use_recommended", "Use recommended", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    class Proceed(Message):
        """User chose to proceed with their override despite the conflict."""

    class UseRecommended(Message):
        """User chose to use the system-recommended model instead."""

        def __init__(self, model_id: str) -> None:
            super().__init__()
            self.model_id = model_id

    class Cancelled(Message):
        """User cancelled the query."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._recommended_model: str = ""

    def show_conflict(
        self,
        override_model: str,
        issue: str,
        recommended_model: str,
        theme: Theme,
    ) -> None:
        self._recommended_model = recommended_model
        self.display = True
        self._render(override_model, issue, recommended_model)
        self.focus()

    def compose(self) -> ComposeResult:
        yield Static("⚠  Override Caution", id="oc-header")
        yield Static("", id="oc-body")
        yield Static(
            "  [p] Proceed anyway   [u] Use recommended   [Esc] Cancel",
            id="oc-footer",
        )

    def action_proceed(self) -> None:
        self.display = False
        self.post_message(self.Proceed())

    def action_use_recommended(self) -> None:
        self.display = False
        self.post_message(self.UseRecommended(self._recommended_model))

    def action_cancel(self) -> None:
        self.display = False
        self.post_message(self.Cancelled())

    def _render(self, override_model: str, issue: str, recommended: str) -> None:
        lines = [
            f"  You've forced: {override_model}",
            "",
            f"  ⚠  {issue}",
            "",
            f"  Recommended model: {recommended}",
        ]
        with contextlib.suppress(Exception):
            self.query_one("#oc-body", Static).update("\n".join(lines))
