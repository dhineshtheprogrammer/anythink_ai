"""BookmarkManager: CRUD operations on a session's bookmark list."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from anythink.bookmarks.models import Bookmark

if TYPE_CHECKING:
    from anythink.providers.base import ChatMessage


class BookmarkManager:
    """Manages a mutable list of bookmarks attached to the running session.

    The ``bookmarks`` list is shared by reference with ``ChatState.bookmarks``
    so any mutation is immediately visible to the TUI (via the state object).
    """

    def __init__(self, bookmarks: list[Bookmark]) -> None:
        self._bm = bookmarks

    # ── write operations ───────────────────────────────────────────────────

    def add(self, turn_index: int, label: str = "") -> Bookmark:
        """Add or replace a bookmark at *turn_index*.

        Replaces any existing bookmark at the same turn so ``/bookmark`` is
        idempotent if called twice on the same turn.
        """
        for i, b in enumerate(self._bm):
            if b.turn_index == turn_index:
                self._bm[i] = Bookmark(turn_index=turn_index, label=label)
                return self._bm[i]
        new = Bookmark(turn_index=turn_index, label=label)
        self._bm.append(new)
        self._bm.sort(key=lambda b: b.turn_index)
        return new

    def remove_by_turn(self, turn_index: int) -> bool:
        """Remove the bookmark at *turn_index*. Returns True if it existed."""
        for i, b in enumerate(self._bm):
            if b.turn_index == turn_index:
                del self._bm[i]
                return True
        return False

    def set_label(self, position: int, label: str) -> bool:
        """Set the label of the bookmark at 1-based *position*.

        Returns True if the bookmark was found.
        """
        bm = self.get_by_position(position)
        if bm is not None:
            bm.label = label
            return True
        return False

    # ── read operations ────────────────────────────────────────────────────

    def get_by_position(self, position: int) -> Bookmark | None:
        """Return the bookmark at 1-based *position*, or None."""
        if 1 <= position <= len(self._bm):
            return self._bm[position - 1]
        return None

    def get_by_turn(self, turn_index: int) -> Bookmark | None:
        """Return the bookmark at *turn_index*, or None."""
        for b in self._bm:
            if b.turn_index == turn_index:
                return b
        return None

    def is_bookmarked(self, turn_index: int) -> bool:
        return any(b.turn_index == turn_index for b in self._bm)

    def list_all(self) -> list[Bookmark]:
        return list(self._bm)

    def count(self) -> int:
        return len(self._bm)

    # ── export ─────────────────────────────────────────────────────────────

    def export_text(
        self,
        messages: list[ChatMessage],
        output_path: Path,
        session_name: str = "",
    ) -> None:
        """Write all bookmarked AI responses to *output_path* as plain text."""
        header = f"Anythink Bookmarks — {session_name or 'unnamed session'}"
        lines: list[str] = [header, "=" * len(header), ""]
        for i, bm in enumerate(self._bm, 1):
            if bm.turn_index >= len(messages):
                continue
            msg = messages[bm.turn_index]
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            label = f"  — {bm.label}" if bm.label else ""
            lines.append(f"[{i}] Turn {bm.turn_index}{label}")
            lines.append(f"Time: {bm.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("")
            lines.append(content)
            lines.append("\n" + "─" * 40 + "\n")
        output_path.write_text("\n".join(lines), encoding="utf-8")

    @classmethod
    def search_sessions(
        cls,
        sessions: Sequence[Any],
        query: str,
    ) -> list[tuple[Any, Bookmark]]:
        """Search bookmark labels across *sessions* for *query*.

        Returns a list of (session, bookmark) pairs where the label contains
        the query string (case-insensitive).
        """
        results: list[tuple[object, Bookmark]] = []
        q = query.lower()
        for session in sessions:
            bmarks = getattr(session, "bookmarks", [])
            for bm in bmarks:
                if q in bm.label.lower():
                    results.append((session, bm))
        return results
