"""Context window usage status bar."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.text import Text

from anythink.ui.hud import _fmt_pct
from anythink.ui.theme import Theme


@dataclass
class ContextStatusBar:
    """Renders a compact context-window usage indicator with color thresholds.

    Color zones match AppConfig thresholds:
      green  < 60%
      yellow 60–84%
      red    85–94%
      bold   ≥ 95%
    """

    theme: Theme
    max_tokens: int
    bar_width: int = field(default=20)

    def render(self, used_tokens: int) -> Text:
        """Return a Rich Text status line for the given token usage."""
        pct = used_tokens / self.max_tokens if self.max_tokens > 0 else 0.0

        if pct < 0.60:
            color = self.theme.success
        elif pct < 0.85:
            color = self.theme.warning
        elif pct < 0.95:
            color = self.theme.error
        else:
            color = "bold red"

        filled = round(pct * self.bar_width)
        bar = "█" * filled + "░" * (self.bar_width - filled)

        t = Text()
        t.append(f"[{bar}] ", style=color)
        t.append(f"Context {_fmt_pct(pct)} ({used_tokens:,}/{self.max_tokens:,})", style=color)
        return t
