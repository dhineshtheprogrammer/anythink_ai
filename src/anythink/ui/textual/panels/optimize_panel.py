"""Full-screen optimization settings overlay — /optimize panel (V4)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from anythink.ui.icons import VS15

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.optimize.models import OptimizeSettings
    from anythink.ui.theme import Theme

# (label, settings_field, choices | None)
_OPT_SETTINGS: list[tuple[str, str, list[str] | None]] = [
    # System
    ("Engine enabled", "enabled", ["on", "off"]),
    ("Mode", "mode", ["auto", "online", "offline"]),
    ("Pre-query micro-prompt", "microprompt_enabled", ["on", "off"]),
    ("Orchestration", "orchestration_mode", ["auto", "deterministic", "meta_llm"]),
    # Routing
    ("Routing strategy", "routing_strategy", ["combined", "category", "token_length"]),
    ("Quality vs reliability", "priority", ["quality", "reliability", "hybrid"]),
    ("User override", "override_allowed", ["on", "off"]),
    # History & Context
    ("History selection mode", "history_mode", ["semantic", "recency", "model_decides"]),
    # Mixing
    ("Default mixing mode", "mixing_mode", ["routing", "ensemble", "chaining", "decompose"]),
    ("Plan Mode", "plan_mode_enabled", ["on", "off"]),
    ("Plan approval required", "plan_approval_required", ["on", "off"]),
    # Rate Limiting
    ("Queue mode", "queue_mode", ["auto", "manual"]),
]


class _OptRow(Static):
    """A single setting row for the OptimizePanel."""

    DEFAULT_CSS = """
    _OptRow { height: 1; padding: 0 2; }
    _OptRow.--highlighted { background: $accent 20%; }
    """

    def __init__(self, label: str, value: str, theme: Theme) -> None:
        super().__init__("")
        self._label = label
        self._value = value
        self._theme = theme
        self._highlighted = False

    def set_highlighted(self, active: bool) -> None:
        self._highlighted = active
        if active:
            self.add_class("--highlighted")
        else:
            self.remove_class("--highlighted")
        self._refresh_row()

    def set_value(self, value: str) -> None:
        self._value = value
        self._refresh_row()

    def on_mount(self) -> None:
        self._refresh_row()

    def _refresh_row(self) -> None:
        t = self._theme
        arrow = "▸ " if self._highlighted else "  "
        label_style = t.secondary if self._highlighted else t.muted
        line = Text()
        line.append(arrow, style=t.accent)
        line.append(f"{self._label:<36}", style=label_style)
        line.append(self._value, style=t.accent if self._highlighted else t.secondary)
        self.update(line)


class OptimizePanel(Widget):
    """Full-screen MMOS settings overlay (mirrors SettingsMenu for AppConfig).

    Reads/writes OptimizeSettings via ctx.mmos_settings.
    """

    can_focus = True

    DEFAULT_CSS = """
    OptimizePanel {
        height: auto;
        max-height: 32;
        border: solid $accent;
        background: $surface;
        display: none;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("up", "prev_row", show=False, priority=True),
        Binding("down", "next_row", show=False, priority=True),
        Binding("escape", "close", show=False, priority=True),
        Binding("q", "close", show=False, priority=True),
        Binding("left", "decrement", show=False, priority=True),
        Binding("right", "increment", show=False, priority=True),
    ]

    class Closed(Message):
        """Posted when the panel is dismissed."""

    class Changed(Message):
        """Posted when any optimization setting changes."""

        def __init__(self, field: str) -> None:
            super().__init__()
            self.field = field

    def __init__(self, ctx: AppContext, theme: Theme, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._ctx = ctx
        self._theme = theme
        self._index = 0

    def open(self) -> None:
        self._index = 0
        self.display = True
        rows = list(self.query(_OptRow))
        s = self._ctx.mmos_settings.get()
        for i, (_, field, _ch) in enumerate(_OPT_SETTINGS):
            if i < len(rows):
                rows[i].set_value(self._value_str(s, field))
                rows[i].set_highlighted(i == 0)
        self.focus()

    def is_open(self) -> bool:
        return self.display

    def compose(self) -> ComposeResult:
        t = self._theme
        s = self._ctx.mmos_settings.get()
        yield Static(Text(f" ⚙{VS15}  Optimization Settings", style=t.primary))
        for i, (label, field, _) in enumerate(_OPT_SETTINGS):
            row = _OptRow(label, self._value_str(s, field), t)
            if i == 0:
                row.set_highlighted(True)
            yield row
        yield Static(Text("  ↑↓ Navigate   ←→ Adjust   Esc Close", style=t.muted))

    def action_prev_row(self) -> None:
        new_idx = max(0, self._index - 1)
        if new_idx != self._index:
            self._index = new_idx
            self._update_highlight()

    def action_next_row(self) -> None:
        new_idx = min(len(_OPT_SETTINGS) - 1, self._index + 1)
        if new_idx != self._index:
            self._index = new_idx
            self._update_highlight()

    def action_close(self) -> None:
        self.display = False
        self.post_message(self.Closed())

    def action_decrement(self) -> None:
        self._adjust(-1)

    def action_increment(self) -> None:
        self._adjust(1)

    def _value_str(self, s: OptimizeSettings, field: str) -> str:
        val = getattr(s, field, None)
        if isinstance(val, bool):
            return "on" if val else "off"
        if val is None:
            return "—"
        return str(val)

    def _adjust(self, direction: int) -> None:
        _, field, choices = _OPT_SETTINGS[self._index]
        s = self._ctx.mmos_settings.get()
        current = getattr(s, field, None)

        if choices:
            current_str = self._value_str(s, field)
            try:
                idx = choices.index(current_str)
            except ValueError:
                idx = 0
            new_str = choices[(idx + direction) % len(choices)]
            new_val: Any = self._parse_value(field, current, new_str)
        else:
            return

        self._ctx.mmos_settings.update(**{field: new_val})
        rows = list(self.query(_OptRow))
        if self._index < len(rows):
            rows[self._index].set_value(self._value_str(self._ctx.mmos_settings.get(), field))
        self.post_message(self.Changed(field))

    def _parse_value(self, field: str, original: Any, text: str) -> Any:
        if isinstance(original, bool):
            return text == "on"
        return text

    def _update_highlight(self) -> None:
        rows = list(self.query(_OptRow))
        for i, row in enumerate(rows):
            row.set_highlighted(i == self._index)
