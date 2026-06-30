"""Chat bubble widgets rendered as Rich Panels inside Textual Static widgets."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static

from anythink.ui.icons import get_icon
from anythink.ui.length import length_indicator
from anythink.ui.theme import Theme
from anythink.ui.timestamp import format_timestamp

if TYPE_CHECKING:
    from anythink.config.schema import AppConfig
    from anythink.optimize.models import TurnMMOSMetadata
    from anythink.rag.models import RetrievalResult
    from anythink.rag.quality import RetrievalQuality
    from anythink.smart.models import SmartResult


# ── helpers ────────────────────────────────────────────────────────────────────


def _surface_style(theme: Theme) -> str:
    """Rich style string that applies the theme's surface tint as a background."""
    return f"on {theme.surface}"


def _user_avatar(theme: Theme) -> str:
    return f"[{theme.primary}]⟨Y⟩[/]"


def _ai_avatar(theme: Theme) -> str:
    return f"[{theme.accent}]✦[/]"


# ── UserBubble ─────────────────────────────────────────────────────────────────


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
        config: AppConfig | None = None,
    ) -> None:
        self._text = text
        self._attachments = attachments or []
        self._created_at = datetime.now()
        self._theme = theme
        self._config = config
        super().__init__("")

    def on_mount(self) -> None:
        self._rebuild()
        self._apply_density()

    # ── public API ─────────────────────────────────────────────────────────────

    def refresh_visual(self, theme: Theme, config: AppConfig | None = None) -> None:
        """Re-render with updated theme and config (called on settings change)."""
        self._theme = theme
        self._config = config
        self._rebuild()
        self._apply_density()

    def refresh_timestamp(self) -> None:
        """Re-render with an updated relative timestamp (called by the 60s ticker)."""
        self._rebuild()

    # ── internals ──────────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        self.update(self._make_renderable())

    def _apply_density(self) -> None:
        if self._config is not None and self._config.density == "compact":
            self.styles.margin = (0, 0, 0, 14)
        else:
            self.styles.margin = (0, 0, 1, 14)

    def _make_renderable(self) -> RenderableType:
        t = self._theme
        cfg = self._config
        ts = format_timestamp(self._created_at, cfg)

        if cfg is not None and cfg.bubble_style == "minimal":
            return self._render_minimal(t, cfg, ts)
        return self._render_boxed(t, cfg, ts)

    def _render_boxed(self, t: Theme, cfg: AppConfig | None, ts: str) -> RenderableType:
        show_avatars = cfg is not None and cfg.show_avatars
        role_label = f"{_user_avatar(t)} You" if show_avatars else "You"
        title = f"[b]{role_label}[/b]"

        lines: list[str] = [self._text]
        for name in self._attachments:
            icon = get_icon("attachment", cfg)
            lines.append(f"{icon} {name}")
        body = "\n".join(lines)

        return Panel(
            Text(body),
            title=title,
            title_align="left",
            subtitle=f"[dim]{ts}[/dim]",
            subtitle_align="right",
            border_style=t.primary,
            style=_surface_style(t),
        )

    def _render_minimal(self, t: Theme, cfg: AppConfig | None, ts: str) -> RenderableType:
        show_avatars = cfg is not None and cfg.show_avatars
        role = f"{_user_avatar(t)} You" if show_avatars else "You"

        header = Text()
        header.append("▎", style=t.primary)
        header.append(role, style=t.primary)
        header.append(f"  {ts}", style=t.muted)

        lines: list[str] = [f"  {self._text}"]
        for name in self._attachments:
            icon = get_icon("attachment", cfg)
            lines.append(f"  {icon} {name}")
        body = Text("\n".join(lines))

        return Group(header, body)


# ── AIBubble ───────────────────────────────────────────────────────────────────


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
        config: AppConfig | None = None,
    ) -> None:
        self._theme = theme
        self._config = config
        self._model_alias = model_alias or "AI"
        self._provider = provider
        self._created_at = datetime.now()
        self._buffer = ""
        self._length_suffix = ""
        self._is_bookmarked = is_bookmarked
        self._retrieval_results: list[RetrievalResult] = []
        self._retrieval_quality: RetrievalQuality | None = None
        self._debug_footer: str = ""
        self._smart_result: SmartResult | None = None
        self._smart_expanded: bool = False
        # Initial streaming placeholder
        super().__init__(Text("▍", style=theme.muted))

    def on_mount(self) -> None:
        self._apply_density()

    # ── streaming helpers ──────────────────────────────────────────────────────

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

    def finalize_with_smart(self, full_text: str, result: SmartResult | None) -> None:
        """Like finalize() but appends an MMAE specialists footer."""
        self._buffer = full_text
        self._smart_result = result
        body: RenderableType = (
            Markdown(full_text) if full_text.strip() else Text("", style=self._theme.muted)
        )
        self._redraw(body)

    def toggle_smart_detail(self) -> None:
        """Expand or collapse the MMAE specialist detail section."""
        self._smart_expanded = not self._smart_expanded
        if self._buffer:
            body: RenderableType = Markdown(self._buffer) if self._buffer.strip() else Text("")
            self._redraw(body)

    def finalize_with_mmos(self, full_text: str, mmos: TurnMMOSMetadata | None) -> None:
        """Like finalize() but prepends an MMOS attribution header line."""
        if mmos is not None:
            header = self._render_attribution_header(mmos)
            self._buffer = full_text
            word_count, symbol = length_indicator(full_text)
            self._length_suffix = f"{word_count:,} words {symbol}"
            body: RenderableType = (
                Markdown(full_text) if full_text.strip() else Text("", style=self._theme.muted)
            )
            self._redraw(Group(header, body))
        else:
            self.finalize(full_text)

    def _render_smart_footer(self, result: SmartResult, t: Theme) -> Text:
        """Render the ✦ N specialists footer (collapsed or expanded)."""
        n = len(result.store.all())
        label = f"specialist{'s' if n != 1 else ''}"
        footer = Text()

        if not self._smart_expanded:
            footer.append(
                f"\n✦ {n} {label} · combined by {result.combiner_model}  ",
                style=t.muted,
            )
            footer.append("[expand]", style=t.accent)
        else:
            footer.append(
                f"\n✦ {n} {label} · combined by {result.combiner_model}  ",
                style=t.muted,
            )
            footer.append("[collapse]", style=t.accent)
            footer.append(
                f"\n  Router: {result.routing_plan.complexity}  "
                f"categories={', '.join(result.routing_plan.categories_detected)}",
                style=t.muted,
            )
            for entry in result.store.all():
                conf = "  ⚠ low confidence" if entry.low_confidence else ""
                footer.append(
                    f"\n  [{entry.slot}] {entry.category} · {entry.model_alias}"
                    f"  score={entry.quality_score}%  {entry.duration_s:.1f}s"
                    f"  retries={entry.retry_count}{conf}",
                    style=t.muted,
                )
                footer.append(f"\n    Q: {entry.sub_question[:80]}", style=t.muted)
            footer.append(
                f"\n  Combiner: {result.combiner_model} · {result.combiner_mode}",
                style=t.muted,
            )
            if result.formatter_applied:
                footer.append(f"\n  Formatter: {result.formatter_applied}", style=t.muted)
            else:
                footer.append("\n  Formatter: not used", style=t.muted)
            footer.append(
                f"\n  Total: {result.total_duration_s:.2f}s",
                style=t.muted,
            )

        return footer

    def _render_attribution_header(self, mmos: TurnMMOSMetadata) -> Text:
        """Produce  ── model · strategy · tokens · elapsed ──  line."""
        t = self._theme
        models_str = ", ".join(mmos.model_ids[:3]) if mmos.model_ids else "?"
        tokens_str = f"{mmos.total_tokens:,} tokens"
        elapsed_str = f"{mmos.elapsed_s:.1f}s"
        line = Text()
        line.append("── ", style=t.muted)
        line.append(models_str, style=t.accent)
        line.append(f"  ·  {mmos.strategy}  ·  {tokens_str}  ·  {elapsed_str}", style=t.muted)
        line.append("  ──", style=t.muted)
        return line

    def show_error(self, message: str) -> None:
        """Replace the bubble content with an error message."""
        self._length_suffix = ""
        icon = get_icon("warning", self._config)
        self._redraw(Text(f"{icon}  {message}", style=self._theme.error))

    def set_retrieval_results(self, results: list[RetrievalResult]) -> None:
        """Attach retrieval sources and refresh the bubble footer."""
        self._retrieval_results = results
        if self._buffer:
            body: RenderableType = Markdown(self._buffer) if self._buffer.strip() else Text("")
            self._redraw(body)

    def set_rag_quality(
        self,
        quality: RetrievalQuality,
        results: list[RetrievalResult],
    ) -> None:
        """Attach retrieval quality + sources; render the enhanced quality footer."""
        self._retrieval_quality = quality
        self._retrieval_results = results
        if self._buffer:
            body: RenderableType = Markdown(self._buffer) if self._buffer.strip() else Text("")
            self._redraw(body)

    def set_debug_footer(self, text: str) -> None:
        """Append a debug footer line (timing/TPS/stop reason) below the bubble."""
        self._debug_footer = text
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

    # ── public API ─────────────────────────────────────────────────────────────

    def refresh_visual(self, theme: Theme, config: AppConfig | None = None) -> None:
        """Re-render with updated theme and config (called on settings change)."""
        self._theme = theme
        self._config = config
        if self._buffer:
            body: RenderableType = Markdown(self._buffer) if self._buffer.strip() else Text("")
        else:
            body = Text("▍", style=theme.muted)
        self._redraw(body)
        self._apply_density()

    def refresh_timestamp(self) -> None:
        """Re-render with an updated relative timestamp."""
        if self._buffer:
            body: RenderableType = Markdown(self._buffer) if self._buffer.strip() else Text("")
            self._redraw(body)

    # ── internals ──────────────────────────────────────────────────────────────

    def _apply_density(self) -> None:
        if self._config is not None and self._config.density == "compact":
            self.styles.margin = (0, 14, 0, 0)
        else:
            self.styles.margin = (0, 14, 1, 0)

    def _make_title(self) -> str:
        t = self._theme
        cfg = self._config
        star = " ✦" if self._is_bookmarked else ""
        show_avatars = cfg is not None and cfg.show_avatars
        avatar = f"{_ai_avatar(t)} " if show_avatars else ""
        return f"[b]{avatar}{self._model_alias}[/b]{star}"

    def _make_subtitle(self) -> str:
        ts = format_timestamp(self._created_at, self._config)
        sub = f"[dim]{self._provider} · {ts}[/dim]"
        if self._length_suffix:
            sub += f"  [dim]{self._length_suffix}[/dim]"
        return sub

    def _redraw(self, body: RenderableType) -> None:
        t = self._theme
        cfg = self._config

        extra_parts: list[RenderableType] = []
        if self._retrieval_results:
            n = len(self._retrieval_results)
            icon = get_icon("rag_footer", cfg)
            if self._retrieval_quality is not None:
                q = self._retrieval_quality
                from anythink.rag.quality import TIER_STYLE
                tier_color = getattr(t, TIER_STYLE.get(q.tier, "muted"), t.muted)
                footer_text = Text()
                footer_text.append(f"\n{icon} {n} source{'s' if n != 1 else ''}  ·  ", style=t.muted)
                footer_text.append(f"Confidence: {q.confidence:.0%}  ·  ", style=t.muted)
                footer_text.append(f"[{q.tier_label}]", style=tier_color)
                extra_parts.append(footer_text)
            else:
                s = "s" if n != 1 else ""
                extra_parts.append(Text(f"\n{icon} Retrieved from {n} source{s}", style=t.muted))
        if self._debug_footer:
            extra_parts.append(Text(f"\n{self._debug_footer}", style=t.muted))

        if self._smart_result is not None and (cfg is None or getattr(cfg, "smart_show_detail", True)):
            extra_parts.append(self._render_smart_footer(self._smart_result, t))

        if extra_parts:
            content: RenderableType = Group(body, *extra_parts)
        else:
            content = body

        if cfg is not None and cfg.bubble_style == "minimal":
            self.update(self._render_minimal(content, t, cfg))
        else:
            self.update(self._render_boxed(content, t))

    def _render_boxed(self, content: RenderableType, t: Theme) -> RenderableType:
        return Panel(
            content,
            title=self._make_title(),
            title_align="left",
            subtitle=self._make_subtitle(),
            subtitle_align="right",
            border_style=t.accent,
            style=_surface_style(t),
        )

    def _render_minimal(
        self, content: RenderableType, t: Theme, cfg: AppConfig | None
    ) -> RenderableType:
        ts = format_timestamp(self._created_at, cfg)
        show_avatars = cfg is not None and cfg.show_avatars
        avatar_part = f"{_ai_avatar(t)} " if show_avatars else ""
        star = " ✦" if self._is_bookmarked else ""

        header = Text()
        header.append("▎", style=t.accent)
        header.append(f"{avatar_part}{self._model_alias}{star}", style=t.accent)
        header.append(f"  {self._provider} · {ts}", style=t.muted)
        if self._length_suffix:
            header.append(f"  {self._length_suffix}", style=t.muted)

        return Group(header, content)


# ── LogoBubble ─────────────────────────────────────────────────────────────────


class LogoBubble(Static):
    """Full-width bubble that displays the ASCII art startup banner."""

    DEFAULT_CSS = """
    LogoBubble {
        margin: 0 0 1 0;
        width: 100%;
    }
    """

    def __init__(self, banner: str, tagline: str, theme: Theme) -> None:
        self._banner = banner
        self._tagline = tagline
        self._theme = theme
        super().__init__("")

    def on_mount(self) -> None:
        self._rebuild()

    def refresh_visual(self, theme: Theme, config: AppConfig | None = None) -> None:
        self._theme = theme
        self._rebuild()

    def _rebuild(self) -> None:
        t = self._theme
        body = Text()
        body.append(self._banner, style=t.primary)
        body.append(f"  {self._tagline}\n", style=t.secondary)
        self.update(Panel(body, border_style=t.muted, style=_surface_style(t)))


# ── SystemBubble ───────────────────────────────────────────────────────────────


class SystemBubble(Static):
    """Centered muted bubble for tool output, slash-command results, and errors."""

    DEFAULT_CSS = """
    SystemBubble {
        margin: 0 8 1 8;
        width: 100%;
    }
    """

    # Maps kind → (icon key, color role name)
    _KIND_MAP: dict[str, tuple[str, str]] = {
        "info": ("info", "muted"),
        "success": ("success", "success"),
        "error": ("error", "error"),
        "warning": ("warning", "warning"),
        "search": ("search", "muted"),
        "code": ("tool", "muted"),
        "rag": ("rag", "muted"),
    }

    def __init__(
        self,
        message: str,
        theme: Theme,
        *,
        kind: str = "info",
        suggestion: str | None = None,
        config: AppConfig | None = None,
    ) -> None:
        self._message = message
        self._kind = kind
        self._suggestion = suggestion
        self._theme = theme
        self._config = config
        super().__init__("")

    def on_mount(self) -> None:
        self._rebuild()

    def refresh_visual(self, theme: Theme, config: AppConfig | None = None) -> None:
        self._theme = theme
        self._config = config
        self._rebuild()

    def set_message(self, message: str) -> None:
        """Update displayed message in-place (used for live progress bubbles)."""
        self._message = message
        self._rebuild()

    def _rebuild(self) -> None:
        t = self._theme
        cfg = self._config
        icon_key, color_role = self._KIND_MAP.get(self._kind, ("info", "muted"))
        icon = get_icon(icon_key, cfg)
        style = getattr(t, color_role, t.muted)

        body = Text()
        body.append(f"{icon}  {self._message}", style=style)
        if self._suggestion:
            body.append(f"\n   → {self._suggestion}", style=t.secondary)

        self.update(Panel(body, border_style=t.muted, style=_surface_style(t)))


# ── CompactNotice ──────────────────────────────────────────────────────────────


class CompactNotice(Static):
    """Single-line borderless confirmation notice (used for session naming)."""

    DEFAULT_CSS = """
    CompactNotice {
        margin: 0 2 0 2;
        height: 1;
    }
    """

    def __init__(self, message: str, theme: Theme, config: AppConfig | None = None) -> None:
        self._message = message
        self._theme = theme
        self._config = config
        super().__init__("")

    def on_mount(self) -> None:
        self._rebuild()

    def refresh_visual(self, theme: Theme, config: AppConfig | None = None) -> None:
        self._theme = theme
        self._config = config
        self._rebuild()

    def _rebuild(self) -> None:
        t = self._theme
        icon = get_icon("success", self._config)
        line = Text()
        line.append(f" {icon} ", style=t.success)
        line.append(self._message, style=t.muted)
        self.update(line)
