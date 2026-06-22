"""Interactive arrow-key-navigable settings overlay."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.ui.theme import Theme

# (label, config_field, choices | None)  — None means free-text / numeric only
_SETTINGS: list[tuple[str, str, list[str] | None]] = [
    # Appearance
    ("Theme", "active_theme", ["midnight", "aurora", "ember", "arctic"]),
    # V2.2: Visual identity
    ("Bubble style",    "bubble_style",  ["boxed", "minimal"]),
    ("Role avatars",    "show_avatars",  ["on", "off"]),
    ("Density",         "density",       ["comfortable", "compact"]),
    ("Timestamps",      "timestamps",    ["relative", "absolute"]),
    ("Icon style",      "icon_style",    ["unicode", "ascii"]),
    # Model & Defaults
    ("Default model alias", "default_model_alias", None),
    # Tools & Agent Behaviour
    ("Web search (default)", "web_search_enabled", ["on", "off"]),
    ("Code execution approval", "exec_mode", ["ask", "auto"]),
    ("Browse approval", "browse_autonomy", ["ask", "auto"]),
    ("Browse mode", "browse_mode", ["http", "headless"]),
    # Context & Warnings
    ("Context warning (yellow)", "context_warning_yellow", None),
    ("Context warning (orange)", "context_warning_orange", None),
    ("Context warning (red)", "context_warning_red", None),
    # V3: Spend tracking
    ("Spend tracking", "spend_tracking", ["on", "off"]),
    ("Spend budget period", "spend_budget_period", ["monthly", "daily"]),
]


class _SettingRow(Static):
    """A single setting row rendered as «▸ Label    value»."""

    DEFAULT_CSS = """
    _SettingRow {
        height: 1;
        padding: 0 2;
    }
    _SettingRow.--highlighted {
        background: $accent 20%;
    }
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
        line.append(f"{self._label:<32}", style=label_style)
        line.append(self._value, style=t.accent if self._highlighted else t.secondary)
        self.update(line)


class SettingsMenu(Widget):
    """Full-screen interactive settings overlay.

    All rows are composed at startup (never dynamically mounted/removed).
    ``open()`` reveals the widget, refreshes values, and takes focus.
    ``action_close()`` / Escape hides it and posts ``SettingsMenu.Closed``.

    Navigate rows with Up/Down; adjust enum values with Left/Right.
    Changes take effect immediately via ConfigManager.save().
    """

    can_focus = True

    DEFAULT_CSS = """
    SettingsMenu {
        height: auto;
        max-height: 26;
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
        Binding("left", "decrement", show=False, priority=True),
        Binding("right", "increment", show=False, priority=True),
    ]

    class Closed(Message):
        """Posted when the settings overlay is dismissed."""

    class Changed(Message):
        """Posted immediately when any config field is saved from the overlay."""

        def __init__(self, field: str) -> None:
            super().__init__()
            self.field = field

    def __init__(self, ctx: AppContext, theme: Theme, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._ctx = ctx
        self._theme = theme
        self._index = 0

    # ── public API ─────────────────────────────────────────────────────────

    def open(self) -> None:
        """Reveal the overlay, refresh all values, and grab keyboard focus."""
        self._index = 0
        self.display = True
        # Update every row to reflect the current config values
        rows = list(self.query(_SettingRow))
        for i, (_, field, _choices) in enumerate(_SETTINGS):
            if i < len(rows):
                rows[i].set_value(self._current_value_str(field))
                rows[i].set_highlighted(i == 0)
        self.focus()

    def is_open(self) -> bool:
        return self.display

    # ── widget composition (static — never rebuilt) ────────────────────────

    def compose(self) -> ComposeResult:
        t = self._theme
        yield Static(Text(" ⚙  Settings", style=t.primary))
        for i, (label, field, _choices) in enumerate(_SETTINGS):
            value = self._current_value_str(field)
            row = _SettingRow(label, value, t)
            if i == 0:
                row.set_highlighted(True)
            yield row
        yield Static(Text("  ↑↓ Navigate   ←→ Adjust   Esc Close", style=t.muted))

    # ── key actions ────────────────────────────────────────────────────────

    def action_prev_row(self) -> None:
        new_idx = max(0, self._index - 1)
        if new_idx != self._index:
            self._index = new_idx
            self._update_highlight()

    def action_next_row(self) -> None:
        new_idx = min(len(_SETTINGS) - 1, self._index + 1)
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

    # ── internals ─────────────────────────────────────────────────────────

    def _current_value_str(self, field: str) -> str:
        """Read a config field and return a human-readable string."""
        val = getattr(self._ctx.config, field, None)
        if isinstance(val, bool):
            return "on" if val else "off"
        if isinstance(val, float):
            return f"{val:.0%}"
        if val is None:
            return "—"
        return str(val)

    def _adjust(self, direction: int) -> None:
        """Cycle enum choices (Left/Right) or nudge a float value."""
        _label, field, choices = _SETTINGS[self._index]
        cfg = self._ctx.config
        current = getattr(cfg, field, None)

        if choices:
            current_str = self._current_value_str(field)
            try:
                idx = choices.index(current_str)
            except ValueError:
                idx = 0
            new_str = choices[(idx + direction) % len(choices)]
            new_val: Any = self._parse_value(field, new_str)
        elif isinstance(current, float):
            new_val = round(max(0.01, min(0.99, current + direction * 0.05)), 2)
        else:
            return  # string/None fields not adjustable via arrows

        new_cfg = replace(cfg, **{field: new_val})
        self._ctx.config_manager.save(new_cfg)
        self._ctx.config = new_cfg
        # Refresh just the row that changed
        rows = list(self.query(_SettingRow))
        if self._index < len(rows):
            rows[self._index].set_value(self._current_value_str(field))
        self.post_message(self.Changed(field))

    def _parse_value(self, field: str, text: str) -> Any:
        original = getattr(self._ctx.config, field, None)
        if isinstance(original, bool):
            return text == "on"
        return text

    def _update_highlight(self) -> None:
        rows = list(self.query(_SettingRow))
        for i, row in enumerate(rows):
            row.set_highlighted(i == self._index)
