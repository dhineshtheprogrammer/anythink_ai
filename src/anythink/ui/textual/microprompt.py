"""Pre-query intent micro-prompt widget (V4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from anythink.optimize.models import QueryIntent

if TYPE_CHECKING:
    from anythink.ui.theme import Theme

_CATEGORIES = ["Coding", "Reasoning", "Creative", "Factual", "Research", "Other"]
_FORMATS = ["Detailed", "Concise", "Step-by-step", "Bullet summary", "Code only"]
_PRIORITIES = ["Quality first", "Speed first"]

_FORMAT_MAP = {
    "Detailed": "detailed",
    "Concise": "concise",
    "Step-by-step": "step_by_step",
    "Bullet summary": "bullet",
    "Code only": "code_only",
}
_PRIORITY_MAP = {
    "Quality first": "quality",
    "Speed first": "speed",
}

_FIELD_OPTIONS = [_CATEGORIES, _FORMATS, _PRIORITIES]
_FIELD_LABELS = ["Question type:", "Answer format:", "Priority:   "]


class MicroPromptWidget(Widget):
    """Inline micro-prompt shown above InputArea after user submits a query.

    Shows three selection rows: category, format, priority.
    User navigates with Tab (field) and Left/Right (option within field).
    Enter confirms; Escape skips (uses session defaults).
    """

    can_focus = True

    DEFAULT_CSS = """
    MicroPromptWidget {
        height: auto;
        max-height: 8;
        border: solid $accent;
        background: $surface;
        display: none;
        padding: 0 2;
    }
    """

    BINDINGS = [
        Binding("enter", "confirm", show=False, priority=True),
        Binding("escape", "skip", show=False, priority=True),
        Binding("tab", "next_field", show=False),
        Binding("shift+tab", "prev_field", show=False),
        Binding("left", "prev_option", show=False),
        Binding("right", "next_option", show=False),
    ]

    class Confirmed(Message):
        """Posted when the user confirms their intent selections."""

        def __init__(self, intent: QueryIntent) -> None:
            super().__init__()
            self.intent = intent

    class Skipped(Message):
        """Posted when the user skips the micro-prompt (uses session defaults)."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._theme: Theme | None = None
        self._field = 0  # 0=category, 1=format, 2=priority
        self._selections = [0, 0, 0]  # index within each field's options

    def show(self, default_category: str, theme: Theme) -> None:
        """Make the widget visible and pre-select the detected category."""
        self._theme = theme
        self._field = 0
        try:
            self._selections[0] = _CATEGORIES.index(default_category)
        except ValueError:
            self._selections[0] = 5  # "Other"
        self._selections[1] = 0
        self._selections[2] = 0
        self.display = True
        self._render()
        self.focus()

    def hide(self) -> None:
        self.display = False

    def compose(self) -> ComposeResult:
        yield Static("[b]Query Intent[/b]", id="mp-header")
        for _label in _FIELD_LABELS:
            yield Static("", classes="mp-row")
        yield Static(
            "  Enter confirm   Esc skip (use defaults)   ← → select   Tab next field",
            id="mp-footer",
        )

    def action_confirm(self) -> None:
        intent = QueryIntent(
            category=_CATEGORIES[self._selections[0]],
            format_preference=_FORMAT_MAP[_FORMATS[self._selections[1]]],
            priority_override=_PRIORITY_MAP[_PRIORITIES[self._selections[2]]],
            from_user=True,
        )
        self.display = False
        self.post_message(self.Confirmed(intent))

    def action_skip(self) -> None:
        self.display = False
        self.post_message(self.Skipped())

    def action_next_field(self) -> None:
        self._field = (self._field + 1) % len(_FIELD_OPTIONS)
        self._render()

    def action_prev_field(self) -> None:
        self._field = (self._field - 1) % len(_FIELD_OPTIONS)
        self._render()

    def action_prev_option(self) -> None:
        opts = _FIELD_OPTIONS[self._field]
        self._selections[self._field] = (self._selections[self._field] - 1) % len(opts)
        self._render()

    def action_next_option(self) -> None:
        opts = _FIELD_OPTIONS[self._field]
        self._selections[self._field] = (self._selections[self._field] + 1) % len(opts)
        self._render()

    def _render(self) -> None:
        import contextlib

        rows = list(self.query(".mp-row"))
        for field_idx, (label, opts) in enumerate(zip(_FIELD_LABELS, _FIELD_OPTIONS, strict=False)):
            if field_idx >= len(rows):
                break
            sel = self._selections[field_idx]
            parts: list[str] = []
            for opt_idx, opt in enumerate(opts):
                if opt_idx == sel:
                    parts.append(f"[b][{opt}][/b]")
                else:
                    parts.append(f" {opt} ")
            active_marker = "▶ " if field_idx == self._field else "  "
            row_text = f"  {active_marker}{label}  {'  '.join(parts)}"
            with contextlib.suppress(Exception):
                rows[field_idx].update(row_text)
