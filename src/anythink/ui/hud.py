"""Persistent two-line Heads-Up Display widget for the Anythink TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widgets import Static

from anythink.ui.icons import get_icon
from anythink.ui.textual.theme_bridge import resolve
from anythink.ui.theme import Theme

if TYPE_CHECKING:
    from anythink.app.chat import ChatState
    from anythink.app.context import AppContext
    from anythink.config.schema import AppConfig


def _fmt_pct(pct: float) -> str:
    """Format a context-window percentage with appropriate precision.

    Exactly 0.0 → "0%".
    Non-zero but < 1 % → one decimal place (e.g. "0.3%").
    ≥ 1 % → whole number (e.g. "12%").
    """
    if pct == 0.0:
        return "0%"
    if pct < 0.01:
        return f"{pct * 100:.1f}%"
    return f"{round(pct * 100)}%"


def _context_bar(
    theme: Theme,
    used: int,
    max_tokens: int,
    *,
    bar_width: int = 16,
    estimated: bool = False,
    yellow: float = 0.60,
    orange: float = 0.85,
    red: float = 0.95,
) -> Text:
    """Build an inline Rich Text context progress bar."""
    pct = used / max_tokens if max_tokens > 0 else 0.0

    if pct < yellow:
        color = theme.success
    elif pct < orange:
        color = theme.warning
    elif pct < red:
        color = theme.error
    else:
        color = "bold red"

    filled = round(pct * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    prefix = "~" if estimated else ""

    t = Text()
    t.append(bar, style=color)
    t.append(f"  {prefix}{used:,}/{max_tokens:,} ({_fmt_pct(pct)})", style=color)
    return t


class HUDWidget(Static):
    """Persistent two-line HUD docked to the top of the screen."""

    DEFAULT_CSS = """
    HUDWidget {
        height: 3;
        dock: top;
        padding: 0 1;
    }
    """

    # ── reactive fields ────────────────────────────────────────────────────────
    app_version: reactive[str] = reactive("", recompose=False)
    session_name: reactive[str] = reactive("")
    branch: reactive[str] = reactive("main")
    theme_name: reactive[str] = reactive("midnight")
    model_alias: reactive[str] = reactive("")
    provider_name: reactive[str] = reactive("")
    tokens_used: reactive[int] = reactive(0)
    tokens_estimated: reactive[bool] = reactive(False)
    context_window: reactive[int] = reactive(0)
    search_enabled: reactive[bool] = reactive(False)
    rag_index: reactive[str] = reactive("")
    session_cost: reactive[float] = reactive(0.0)

    def __init__(self, theme: Theme, version: str, **kwargs: object) -> None:
        super().__init__("", **kwargs)  # type: ignore[arg-type]
        self._theme = theme
        self._version = version
        self._warn_yellow: float = 0.60
        self._warn_orange: float = 0.85
        self._warn_red: float = 0.95
        self._icon_style: str = "unicode"

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        t = self._theme
        self.styles.border_bottom = ("solid", resolve(t.muted))
        self.app_version = self._version
        self.theme_name = t.name

    def on_resize(self, event: events.Resize) -> None:
        self._refresh_hud()

    # ── reactive watchers ──────────────────────────────────────────────────────

    def watch_session_name(self) -> None:
        self._refresh_hud()

    def watch_branch(self) -> None:
        self._refresh_hud()

    def watch_theme_name(self) -> None:
        self._refresh_hud()

    def watch_model_alias(self) -> None:
        self._refresh_hud()

    def watch_provider_name(self) -> None:
        self._refresh_hud()

    def watch_tokens_used(self) -> None:
        self._refresh_hud()

    def watch_tokens_estimated(self) -> None:
        self._refresh_hud()

    def watch_context_window(self) -> None:
        self._refresh_hud()

    def watch_search_enabled(self) -> None:
        self._refresh_hud()

    def watch_rag_index(self) -> None:
        self._refresh_hud()

    def watch_session_cost(self) -> None:
        self._refresh_hud()

    # ── public API ─────────────────────────────────────────────────────────────

    def update_from_state(self, ctx: AppContext, state: ChatState) -> None:
        """Sync all reactive fields from *ctx* and *state* in one call."""
        self.session_name = state.session_name or ""
        self.model_alias = state.model_id
        self.provider_name = state.provider.display_name
        self.tokens_used = state.total_tokens_used
        self.tokens_estimated = state.tokens_estimated
        self.context_window = state.context_window
        self.search_enabled = state.search_enabled
        self.rag_index = ctx.config.active_rag_index or ""
        self.theme_name = ctx.config.active_theme
        self._warn_yellow = ctx.config.context_warning_yellow
        self._warn_orange = ctx.config.context_warning_orange
        self._warn_red = ctx.config.context_warning_red
        self._icon_style = ctx.config.icon_style

    # ── rendering ─────────────────────────────────────────────────────────────

    def _refresh_hud(self) -> None:
        try:
            _ = self.app
        except Exception:
            return
        try:
            w = self.size.width
        except Exception:
            w = 100
        content = Text()
        content.append_text(self._line1(w))
        content.append("\n")
        content.append_text(self._line2(w))
        self.update(content)

    def _cfg_stub(self) -> AppConfig | None:
        """Return a minimal config-like object for icon resolution."""

        class _Stub:
            icon_style = self._icon_style

        return _Stub()  # type: ignore[return-value]

    def _line1(self, width: int = 100) -> Text:
        t = self._theme
        sep = Text("  │  ", style=t.muted)
        line = Text()

        line.append(" ✦ Anythink  ", style=t.primary)
        line.append(f"v{self.app_version}", style=t.secondary)
        line.append_text(sep)

        session_label = f'"{self.session_name}"' if self.session_name else "(no name)"
        line.append("Session: ", style=t.muted)
        line.append(session_label, style=t.secondary)
        line.append_text(sep)

        if width >= 60:
            line.append("Branch: ", style=t.muted)
            line.append(self.branch, style=t.secondary)
            line.append_text(sep)

        if width >= 80:
            line.append("Theme: ", style=t.muted)
            line.append(self.theme_name.capitalize(), style=t.secondary)

        return line

    def _line2(self, width: int = 100) -> Text:
        t = self._theme
        cfg = self._cfg_stub()
        sep = Text("  │  ", style=t.muted)
        line = Text()

        bar_width = 16 if width >= 100 else (10 if width >= 80 else 6)

        if self.model_alias:
            line.append("Model: ", style=t.muted)
            line.append(self.model_alias, style=t.accent)
            line.append_text(sep)

        if self.provider_name:
            if width >= 80:
                line.append("Provider: ", style=t.muted)
                line.append(f"{self.provider_name} ", style=t.accent)
            dot = get_icon("dot", cfg)
            line.append(dot, style=t.success)
            line.append_text(sep)

        if self.context_window > 0:
            line.append("Context: ", style=t.muted)
            line.append_text(
                _context_bar(
                    t,
                    self.tokens_used,
                    self.context_window,
                    bar_width=bar_width,
                    estimated=self.tokens_estimated,
                    yellow=self._warn_yellow,
                    orange=self._warn_orange,
                    red=self._warn_red,
                )
            )
            line.append_text(sep)

        search_icon = get_icon("search", cfg)
        search_style = t.success if self.search_enabled else t.muted
        if width >= 60:
            line.append(f"{search_icon} Search: ", style=t.muted)
            search_label = "ON" if self.search_enabled else "OFF"
        else:
            line.append(f"{search_icon} ", style=t.muted)
            search_label = "ON" if self.search_enabled else "—"
        line.append(search_label, style=search_style)
        line.append_text(sep)

        rag_icon = get_icon("rag", cfg)
        rag_style = t.success if self.rag_index else t.muted
        rag_label = self.rag_index if self.rag_index else "—"
        if width >= 60:
            line.append(f"{rag_icon} RAG: ", style=t.muted)
        else:
            line.append(f"{rag_icon} ", style=t.muted)
        line.append(rag_label, style=rag_style)

        if self.session_cost > 0:
            line.append_text(sep)
            line.append("~$", style=t.muted)
            line.append(f"{self.session_cost:.4f}", style=t.muted)

        return line
