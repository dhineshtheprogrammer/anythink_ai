"""BranchManager: create, switch, and inspect conversation branches."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anythink.app.chat import ChatState


_MAIN = "main"


class BranchManager:
    """Provides branching operations on a ``ChatState``.

    The manager mutates ``state`` in-place:
    - ``state.history`` always points to the active branch's message list.
    - ``state.bookmarks`` always points to the active branch's bookmark list.
    - ``state.active_branch`` holds the current branch name.
    """

    def __init__(self, state: ChatState) -> None:
        self._state = state
        self._ensure_main()

    # ── public API ─────────────────────────────────────────────────────────

    def create_branch(self) -> str:
        """Fork from the current turn. Returns the new branch name.

        The new branch starts as a copy of the current history up to the
        divergence point.  New messages go into the new branch only.
        """
        state = self._state
        n = len(state.branches)  # unique sequential number
        name = f"Branch {n}"

        diverge_at = len(state.history)
        new_msgs = list(state.history)  # copy up to divergence
        state.branches[name] = new_msgs
        state.branch_bookmarks[name] = []
        state.branch_diverges[name] = diverge_at

        self._switch_to(name)
        return name

    def switch_to(self, name: str) -> bool:
        """Switch the active branch to *name*.  Returns False if not found."""
        if name not in self._state.branches:
            return False
        self._switch_to(name)
        return True

    def list_branches(self) -> list[dict[str, object]]:
        """Return display info for all branches, sorted by name."""
        state = self._state
        rows: list[dict[str, object]] = []
        for name, msgs in state.branches.items():
            non_sys = [m for m in msgs if m.role != "system"]
            rows.append(
                {
                    "name": name,
                    "diverge_turn": state.branch_diverges.get(name, 0),
                    "message_count": len(non_sys),
                    "is_current": name == state.active_branch,
                }
            )
        # main first, then branches in creation order
        return sorted(rows, key=lambda r: (r["name"] != _MAIN, r["name"]))

    def branch_names(self) -> list[str]:
        return list(self._state.branches.keys())

    # ── internal helpers ───────────────────────────────────────────────────

    def _ensure_main(self) -> None:
        """Bootstrap the ``main`` branch if this is a fresh ChatState."""
        state = self._state
        if _MAIN not in state.branches:
            state.branches[_MAIN] = state.history
            state.branch_bookmarks[_MAIN] = state.bookmarks
            state.branch_diverges[_MAIN] = 0

    def _switch_to(self, name: str) -> None:
        """Low-level branch switch — does not validate *name*."""
        state = self._state
        # Persist current branch's mutable state
        state.branches[state.active_branch] = state.history
        state.branch_bookmarks[state.active_branch] = state.bookmarks

        # Activate the target branch
        state.active_branch = name
        state.history = state.branches[name]
        state.bookmarks = state.branch_bookmarks.get(name, [])
        # Normalise bookmarks list if somehow missing
        if name not in state.branch_bookmarks:
            state.branch_bookmarks[name] = state.bookmarks
