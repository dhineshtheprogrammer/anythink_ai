"""Live rate-limit status overlay panel (V4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.ui.theme import Theme


class RateLimitPanel(Widget):
    """Live-updating overlay that shows per-model rate limit status.

    Auto-refreshes every second via set_interval. Opened by /optimize ratelimit.
    """

    can_focus = True

    DEFAULT_CSS = """
    RateLimitPanel {
        height: auto;
        max-height: 24;
        border: solid $accent;
        background: $surface;
        display: none;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("escape", "close", show=False, priority=True),
        Binding("q", "close", show=False, priority=True),
        Binding("r", "reset_counters", "Reset counters", show=True),
    ]

    class Closed(Message):
        """Posted when the panel is dismissed."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._ctx: AppContext | None = None
        self._theme: Theme | None = None

    def open(self, ctx: AppContext, theme: Theme) -> None:
        """Open and start the 1-second refresh timer."""
        self._ctx = ctx
        self._theme = theme
        self.display = True
        self._refresh_data()
        self.set_interval(1.0, self._refresh_data)
        self.focus()

    def compose(self) -> ComposeResult:
        yield Static("[b]Rate Limit Status[/b]", id="rl-header")
        yield Static("Loading…", id="rl-body")
        yield Static("  r Reset counters   Esc Close", id="rl-footer")

    def action_close(self) -> None:
        self.display = False
        self.post_message(self.Closed())

    def action_reset_counters(self) -> None:
        if self._ctx is not None:
            self._ctx.rate_limit_manager.reset_counters()
            self._refresh_data()

    def _refresh_data(self) -> None:
        if self._ctx is None or self._theme is None:
            return

        import contextlib

        windows = self._ctx.rate_limit_manager.get_status()
        registry = self._ctx.mmos_registry

        lines: list[str] = [
            f"  {'Model':<38} {'RPM':>6}  {'TPM':>8}  {'RPD':>6}  Status",
            "  " + "─" * 70,
        ]

        for window in sorted(windows, key=lambda w: w.model_id):
            cap = registry.get(window.model_id)
            rpm_lim = cap.rpm_limit if cap else None
            tpm_lim = cap.tpm_limit if cap else None
            rpd_lim = cap.rpd_limit if cap else None

            rpm_str = f"{window.requests_in_window}/{rpm_lim}" if rpm_lim else "—"
            tpm_str = f"{window.tokens_in_window}/{tpm_lim}" if tpm_lim else "—"
            rpd_str = f"{window.requests_today}/{rpd_lim}" if rpd_lim else "—"

            if window.unavailable:
                status = "UNAVAILABLE"
            elif rpm_lim and window.requests_in_window >= rpm_lim:
                status = "AT LIMIT"
            elif rpd_lim and window.requests_today >= rpd_lim:
                status = "DAILY LIMIT"
            elif window.requests_in_window > 0:
                status = "ACTIVE"
            else:
                tier = cap.tier if cap else "?"
                status = "LOCAL" if tier == "local" else "STANDBY"

            lines.append(
                f"  {window.model_id:<38} {rpm_str:>6}  {tpm_str:>8}  {rpd_str:>6}  {status}"
            )

        fb_order = self._ctx.mmos_settings.get().fallback_order
        fallback_str = " → ".join(fb_order) if fb_order else "(none set)"
        lines += [
            "  " + "─" * 70,
            f"  Fallback order: {fallback_str}",
        ]

        with contextlib.suppress(Exception):
            self.query_one("#rl-body", Static).update("\n".join(lines))
