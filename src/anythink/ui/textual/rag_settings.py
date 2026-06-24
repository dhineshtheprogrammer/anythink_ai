"""Interactive arrow-key-navigable RAG settings overlay.

Mirrors ``settings_menu.py`` architecture with two data sources:
  - ``IndexInfo`` (per-active-index settings, saved to YAML)
  - ``AppConfig``  (global RAG settings, saved via ConfigManager)

Read-only rows (source path, dimensions, storage path) are shown but cannot
be adjusted.  Fields that require a full rebuild (chunk strategy, embedding
model, vector backend) display a ``⚠ rebuild`` suffix when changed.

Usage in the TUI:
  1. Compose ``RAGSettingsMenu(ctx, theme, id="rag-settings-menu")`` in the
     widget tree (always present, hidden by CSS ``display: none``).
  2. Call ``open()`` to reveal and focus.
  3. ``RAGSettingsMenu.Closed`` is posted on Esc / action_close().
  4. ``RAGSettingsMenu.Changed`` is posted on every save (field, requires_rebuild).
"""

from __future__ import annotations

from dataclasses import replace
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
    from anythink.ui.theme import Theme

# ── Row definitions ───────────────────────────────────────────────────────────
#
# Each tuple: (label, source, field, choices_or_none, rebuild_required)
#   source:
#     "section"      — non-navigable header (rendered differently)
#     "index"        — reads/writes active IndexInfo
#     "config"       — reads/writes AppConfig
#     "readonly_idx" — reads IndexInfo, not adjustable
#     "readonly_cfg" — reads AppConfig, not adjustable
#     "index_sel"    — special: cycles through available index names

_RAG_ROWS: list[tuple[str, str, str, list[str] | None, bool]] = [
    # ── Active Index ──────────────────────────────────────────────────────────
    ("── Active Index ──", "section", "", None, False),
    ("Selected index", "index_sel", "name", None, False),
    ("Source path", "readonly_idx", "source_path", None, False),
    # ── Chunking ─────────────────────────────────────────────────────────────
    ("── Chunking ──", "section", "", None, False),
    (
        "Chunk strategy",
        "index",
        "chunk_strategy",
        ["fixed", "sentence", "paragraph", "semantic", "code", "heading"],
        True,
    ),
    ("Chunk size (tokens)", "index", "chunk_size", None, True),
    ("Chunk overlap (tokens)", "index", "chunk_overlap", ["80", "100", "150", "200", "300"], True),
    # ── Embedding ─────────────────────────────────────────────────────────────
    ("── Embedding ──", "section", "", None, False),
    ("Embedding model", "index", "embedding_backend", None, True),  # choices built at open()
    # ── Vector Store ──────────────────────────────────────────────────────────
    ("── Vector Store ──", "section", "", None, False),
    (
        "Vector backend",
        "index",
        "vector_backend",
        ["pure", "faiss", "chroma", "lance", "pinecone", "azure"],
        True,
    ),
    # ── Retrieval ─────────────────────────────────────────────────────────────
    ("── Retrieval ──", "section", "", None, False),
    (
        "Retrieval strategy",
        "index",
        "retrieval_strategy",
        ["vector", "bm25", "hybrid", "mmr"],
        False,
    ),
    ("Chunks per query", "index", "top_k", None, False),
    ("Re-ranking", "index", "reranking_enabled", ["on", "off"], False),
    (
        "Re-ranking model",
        "index",
        "reranking_model",
        ["bge-reranker-base", "bge-reranker-large", "cohere-rerank"],
        False,
    ),
    ("Relevance threshold", "index", "quality_threshold", None, False),
    # ── Quality & Fallback ────────────────────────────────────────────────────
    ("── Quality ──", "section", "", None, False),
    ("Quality indicators", "config", "rag_quality_indicators", ["on", "off"], False),
    ("No-match behavior", "config", "rag_no_match_behavior", ["graceful", "passthrough"], False),
    ("Confidence display", "config", "rag_confidence_display", ["on", "off"], False),
]

# Indices of rows that are NOT sections (navigable)
_NAVIGABLE = [i for i, (_, src, _, _, _) in enumerate(_RAG_ROWS) if src != "section"]


# ── Row widget ────────────────────────────────────────────────────────────────


class _RagRow(Static):
    """One settings row: «▸ Label    value [⚠]»."""

    DEFAULT_CSS = """
    _RagRow {
        height: 1;
        padding: 0 2;
    }
    _RagRow.--highlighted {
        background: $accent 20%;
    }
    _RagRow.--section {
        color: $muted;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        label: str,
        value: str,
        theme: Theme,
        *,
        is_section: bool = False,
        readonly: bool = False,
        rebuild: bool = False,
    ) -> None:
        super().__init__("")
        self._label = label
        self._value = value
        self._theme = theme
        self._is_section = is_section
        self._readonly = readonly
        self._rebuild = rebuild
        self._highlighted = False

    def set_highlighted(self, active: bool) -> None:
        self._highlighted = active
        if active:
            self.add_class("--highlighted")
        else:
            self.remove_class("--highlighted")
        self._refresh()

    def set_value(self, value: str, *, rebuild_pending: bool = False) -> None:
        self._value = value
        self._rebuild = rebuild_pending
        self._refresh()

    def on_mount(self) -> None:
        if self._is_section:
            self.add_class("--section")
        self._refresh()

    def _refresh(self) -> None:
        t = self._theme
        if self._is_section:
            self.update(Text(f"  {self._label}", style=t.muted))
            return

        arrow = "▸ " if self._highlighted else "  "
        label_style = t.secondary if self._highlighted else t.muted
        val_style = t.accent if self._highlighted else t.secondary

        line = Text()
        line.append(arrow, style=t.accent)
        line.append(f"{self._label:<34}", style=label_style)
        if self._readonly:
            line.append(self._value[:36], style=t.muted)
            line.append(" [ro]", style=t.muted)
        else:
            line.append(self._value[:36], style=val_style)
            if self._rebuild:
                line.append("  ⚠ rebuild", style=t.warning)
        self.update(line)


# ── Main overlay widget ───────────────────────────────────────────────────────


class RAGSettingsMenu(Widget):
    """Full-screen interactive RAG settings overlay.

    ``open()`` reveals the widget, refreshes all values, and takes focus.
    ``action_close()`` / Escape hides it and posts ``RAGSettingsMenu.Closed``.

    Navigate with Up/Down; adjust enum values with Left/Right.
    Numeric values (chunk_size, top_k, quality_threshold) are nudged by
    Left/Right at fixed increments.
    """

    can_focus = True

    DEFAULT_CSS = """
    RAGSettingsMenu {
        height: auto;
        max-height: 30;
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
        """Posted when the RAG settings overlay is dismissed."""

    class Changed(Message):
        """Posted when any setting is saved."""

        def __init__(self, field: str, requires_rebuild: bool = False) -> None:
            super().__init__()
            self.field = field
            self.requires_rebuild = requires_rebuild

    def __init__(self, ctx: AppContext, theme: Theme, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._ctx = ctx
        self._theme = theme
        self._nav_index = 0  # index into _NAVIGABLE
        self._embed_choices: list[str] = []
        self._rebuild_pending: set[str] = set()

    # ── public API ─────────────────────────────────────────────────────────

    def open(self) -> None:
        """Reveal the overlay and refresh all values."""
        self._embed_choices = self._ctx.embedding_registry.names() or ["local", "mock"]
        self._nav_index = 0
        self._rebuild_pending = set()
        self.display = True
        self._refresh_all_rows()
        self.focus()

    def is_open(self) -> bool:
        return self.display

    # ── widget composition ─────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        t = self._theme
        yield Static(Text(f" ⚙{VS15}  RAG Settings", style=t.primary))
        for label, source, field, _choices, rebuild in _RAG_ROWS:
            is_section = source == "section"
            readonly = source in ("readonly_idx", "readonly_cfg")
            row = _RagRow(label, "", t, is_section=is_section, readonly=readonly, rebuild=False)
            yield row
        yield Static(Text("  ↑↓ Navigate   ←→ Adjust   Esc Close", style=t.muted))

    # ── key actions ────────────────────────────────────────────────────────

    def action_prev_row(self) -> None:
        new_idx = max(0, self._nav_index - 1)
        if new_idx != self._nav_index:
            self._nav_index = new_idx
            self._update_highlight()

    def action_next_row(self) -> None:
        new_idx = min(len(_NAVIGABLE) - 1, self._nav_index + 1)
        if new_idx != self._nav_index:
            self._nav_index = new_idx
            self._update_highlight()

    def action_close(self) -> None:
        self._rebuild_pending.clear()
        self.display = False
        self.post_message(self.Closed())

    def action_decrement(self) -> None:
        self._adjust(-1)

    def action_increment(self) -> None:
        self._adjust(1)

    # ── internals ─────────────────────────────────────────────────────────

    def _row_index(self) -> int:
        """Return the _RAG_ROWS index for the currently highlighted row."""
        return _NAVIGABLE[self._nav_index]

    def _all_rows(self) -> list[_RagRow]:
        return list(self.query(_RagRow))

    def _refresh_all_rows(self) -> None:
        rows = self._all_rows()
        for dom_idx, (label, source, field, _choices, rebuild) in enumerate(_RAG_ROWS):
            if dom_idx >= len(rows):
                break
            nav_pos = _NAVIGABLE.index(dom_idx) if dom_idx in _NAVIGABLE else -1
            highlighted = nav_pos == self._nav_index
            rows[dom_idx].set_highlighted(highlighted)
            if source == "section":
                continue
            rows[dom_idx].set_value(
                self._read_value(source, field),
                rebuild_pending=field in self._rebuild_pending,
            )

    def _update_highlight(self) -> None:
        rows = self._all_rows()
        for nav_pos, row_idx in enumerate(_NAVIGABLE):
            if row_idx < len(rows):
                rows[row_idx].set_highlighted(nav_pos == self._nav_index)

    def _read_value(self, source: str, field: str) -> str:
        rm = self._ctx.rag_manager
        info = rm.get_info(rm.active_name) if rm.active_name else None

        if source in ("index", "readonly_idx", "index_sel"):
            if info is None:
                return "— (no active index)"
            if field == "name":
                return info.name
            val = getattr(info, field, None)
        elif source in ("config", "readonly_cfg"):
            val = getattr(self._ctx.config, field, None)
        else:
            return ""

        if field == "embedding_backend":
            return str(val) if val else "local"
        if isinstance(val, bool):
            return "on" if val else "off"
        if isinstance(val, float):
            return f"{val:.2f}"
        if val is None:
            return "—"
        return str(val)

    def _choices_for(self, row_idx: int) -> list[str]:
        label, source, field, choices, _ = _RAG_ROWS[row_idx]
        if field == "embedding_backend":
            return self._embed_choices
        if choices:
            return choices
        return []

    def _adjust(self, direction: int) -> None:
        row_idx = self._row_index()
        label, source, field, choices_raw, rebuild = _RAG_ROWS[row_idx]

        # Read-only and section rows do nothing
        if source in ("section", "readonly_idx", "readonly_cfg"):
            return

        # Special: cycle through available index names
        if source == "index_sel":
            self._cycle_active_index(direction)
            return

        rm = self._ctx.rag_manager
        info = rm.get_info(rm.active_name) if rm.active_name else None

        if source == "index" and info is None:
            return  # no active index — can't edit per-index settings

        choices = self._choices_for(row_idx)

        if choices:
            current_str = self._read_value(source, field)
            try:
                idx = choices.index(current_str)
            except ValueError:
                idx = 0
            new_str = choices[(idx + direction) % len(choices)]
            new_val: Any = self._parse_to_type(source, field, new_str, info)
        else:
            # Numeric adjustment
            new_val = self._nudge_numeric(source, field, direction, info)
            if new_val is None:
                return

        self._save_value(source, field, new_val, info, rebuild)

    def _nudge_numeric(
        self,
        source: str,
        field: str,
        direction: int,
        info: Any,
    ) -> Any | None:
        """Nudge a numeric config value by one step."""
        if source == "index" and info:
            current = getattr(info, field, None)
        elif source == "config":
            current = getattr(self._ctx.config, field, None)
        else:
            return None

        if field == "chunk_size":
            step = 64
            return max(256, min(2048, int(current) + direction * step))
        if field == "chunk_overlap":
            step = 20
            return max(20, min(500, int(current) + direction * step))
        if field == "top_k":
            return max(1, min(20, int(current) + direction))
        if field == "quality_threshold":
            return round(max(0.0, min(1.0, float(current) + direction * 0.05)), 2)
        if field == "rag_top_k":
            return max(1, min(20, int(current) + direction))
        if field == "rag_threshold":
            return round(max(0.0, min(1.0, float(current) + direction * 0.05)), 2)
        return None

    def _parse_to_type(
        self,
        source: str,
        field: str,
        text: str,
        info: Any,
    ) -> Any:
        """Convert string choice back to the correct Python type."""
        if source == "index" and info is not None:
            original = getattr(info, field, None)
        else:
            original = getattr(self._ctx.config, field, None)

        if isinstance(original, bool):
            return text == "on"
        return text

    def _save_value(
        self,
        source: str,
        field: str,
        new_val: Any,
        info: Any,
        rebuild: bool,
    ) -> None:
        rm = self._ctx.rag_manager
        rows = self._all_rows()
        row_idx = self._row_index()

        if source == "index" and info is not None:
            from dataclasses import replace as _replace

            updated = _replace(info, **{field: new_val})
            rm.create_index(updated)
            if rm.active_name == info.name:
                rm._active_info = updated  # noqa: SLF001

        elif source == "config":
            from dataclasses import replace as _replace

            new_cfg = _replace(self._ctx.config, **{field: new_val})
            self._ctx.config_manager.save(new_cfg)
            self._ctx.config = new_cfg

        if rebuild:
            self._rebuild_pending.add(field)

        if row_idx < len(rows):
            rows[row_idx].set_value(
                self._read_value(source, field),
                rebuild_pending=field in self._rebuild_pending,
            )
        self.post_message(self.Changed(field, requires_rebuild=rebuild))

    def _cycle_active_index(self, direction: int) -> None:
        """Cycle through available indexes and activate the selected one."""
        rm = self._ctx.rag_manager
        indexes = rm.list_indexes()
        if not indexes:
            return
        names = [i.name for i in indexes]
        current = rm.active_name or ""
        try:
            idx = names.index(current)
        except ValueError:
            idx = 0
        new_name = names[(idx + direction) % len(names)]
        if new_name != current:
            rm.use_index(new_name)
            from dataclasses import replace as _replace

            new_cfg = _replace(self._ctx.config, active_rag_index=new_name)
            self._ctx.config_manager.save(new_cfg)
            self._ctx.config = new_cfg
            # Refresh all rows since source_path, etc. change with the index
            self._refresh_all_rows()
            self.post_message(self.Changed("active_index"))
