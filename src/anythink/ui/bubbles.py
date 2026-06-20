"""Chat bubble widgets rendered as Rich Panels inside Textual Static widgets."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static

from anythink.ui.length import length_indicator
from anythink.ui.theme import Theme

if TYPE_CHECKING:
    from anythink.rag.models import RetrievalResult


class UserBubble(Static):
    """Right-aligned bordered bubble for a user message."""

    DEFAULT_CSS = """
    UserBubble {
        margin: 0 0 1 14;
        width: 100%;
    }
    """

    def __init__(
        self,
        text: str,
        theme: Theme,
        attachments: list[str] | None = None,
    ) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        lines: list[str] = [text]
        for name in attachments or []:
            lines.append(f"\U0001f4ce {name}")
        body = "\n".join(lines)
        panel = Panel(
            Text(body),
            title="[b]You[/b]",
            title_align="left",
            subtitle=f"[dim]{timestamp}[/dim]",
            subtitle_align="right",
            border_style=theme.primary,
        )
        super().__init__(panel)
        self._theme = theme


class AIBubble(Static):
    """Left-aligned bordered bubble for an AI response.

    Supports incremental text updates during streaming (``append_text``),
    final Markdown rendering (``finalize``), and error display.
    """

    DEFAULT_CSS = """
    AIBubble {
        margin: 0 14 1 0;
        width: 100%;
    }
    """

    def __init__(
        self,
        theme: Theme,
        *,
        model_alias: str = "",
        provider: str = "",
        is_bookmarked: bool = False,
    ) -> None:
        self._theme = theme
        self._model_alias = model_alias or "AI"
        self._provider = provider
        self._timestamp = datetime.now().strftime("%H:%M:%S")
        self._buffer = ""
        self._length_suffix = ""  # set by finalize(); empty during streaming
        self._is_bookmarked = is_bookmarked
        self._retrieval_results: list[RetrievalResult] = []
        panel = Panel(
            Text("▍", style=theme.muted),
            title=self._make_title(),
            title_align="left",
            subtitle=f"[dim]{self._provider} · {self._timestamp}[/dim]",
            subtitle_align="right",
            border_style=theme.accent,
        )
        super().__init__(panel)

    # ── streaming helpers ──────────────────────────────────────────────────

    def append_text(self, chunk: str) -> None:
        """Append a streaming chunk and refresh with accumulated plain text."""
        self._buffer += chunk
        self._redraw(Text(self._buffer, style=self._theme.primary))

    def finalize(self, full_text: str) -> None:
        """Replace live plain text with Rich-rendered Markdown and add length indicator."""
        self._buffer = full_text
        word_count, symbol = length_indicator(full_text)
        self._length_suffix = f"{word_count:,} words {symbol}"
        body: RenderableType = (
            Markdown(full_text) if full_text.strip() else Text("", style=self._theme.muted)
        )
        self._redraw(body)

    def show_error(self, message: str) -> None:
        """Replace the bubble content with an error message."""
        self._length_suffix = ""
        self._redraw(Text(f"⚠  {message}", style=self._theme.error))

    def set_retrieval_results(self, results: list[RetrievalResult]) -> None:
        """Attach retrieval sources and refresh the bubble footer."""
        self._retrieval_results = results
        # Re-render the current buffer with the new footer
        if self._buffer:
            body: RenderableType = Markdown(self._buffer) if self._buffer.strip() else Text("")
            self._redraw(body)

    def mark_bookmarked(self) -> None:
        """Add the bookmark indicator (✦) to the bubble title."""
        self._is_bookmarked = True
        self._redraw(Text(self._buffer, style=self._theme.primary) if self._buffer else Text(""))

    def clear_bookmark(self) -> None:
        """Remove the bookmark indicator from the bubble title."""
        self._is_bookmarked = False
        self._redraw(Text(self._buffer, style=self._theme.primary) if self._buffer else Text(""))

    def _make_title(self) -> str:
        star = " ✦" if self._is_bookmarked else ""
        return f"[b]{self._model_alias}[/b]{star}"

    def _redraw(self, body: RenderableType) -> None:
        subtitle = f"[dim]{self._provider} · {self._timestamp}[/dim]"
        if self._length_suffix:
            subtitle += f"  [dim]{self._length_suffix}[/dim]"

        # Attach RAG retrieval footer when sources are available
        if self._retrieval_results:
            n = len(self._retrieval_results)
            footer_text = Text(
                f"\n\U0001f4da Retrieved from {n} source{'s' if n != 1 else ''}",
                style=self._theme.muted,
            )
            content: RenderableType = Group(body, footer_text)
        else:
            content = body

        panel = Panel(
            content,
            title=self._make_title(),
            title_align="left",
            subtitle=subtitle,
            subtitle_align="right",
            border_style=self._theme.accent,
        )
        self.update(panel)


class SystemBubble(Static):
    """Centered muted bubble for tool output, slash-command results, and errors."""

    DEFAULT_CSS = """
    SystemBubble {
        margin: 0 8 1 8;
        width: 100%;
    }
    """

    _ICONS: dict[str, str] = {
        "info": "ℹ️",
        "success": "✅",
        "error": "❌",
        "warning": "⚠️",
        "search": "\U0001f50d",
        "code": "⚙️",
        "rag": "\U0001f4da",
    }

    def __init__(
        self,
        message: str,
        theme: Theme,
        *,
        kind: str = "info",
    ) -> None:
        icon = self._ICONS.get(kind, "ℹ️")
        style = theme.error if kind == "error" else theme.muted
        panel = Panel(
            Text(f"{icon}  {message}", style=style),
            border_style=theme.muted,
        )
        super().__init__(panel)
        self._theme = theme
        self._kind = kind
