"""Tests for BranchManager and conversation branching."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from anythink.app.chat import ChatState, _build_session
from anythink.branch.manager import BranchManager
from anythink.branch.models import BranchInfo
from anythink.providers.base import ChatMessage, StreamChunk


def _make_provider() -> object:
    p = MagicMock()
    p.name = "mock"
    p.display_name = "Mock"
    p.requires_api_key = False
    return p


def _make_state(messages: list[ChatMessage] | None = None) -> ChatState:
    state = ChatState(
        provider=_make_provider(),  # type: ignore[arg-type]
        model_id="test-model",
        context_window=4096,
    )
    if messages:
        state.history.extend(messages)
        # Keep branches["main"] in sync (same object via __post_init__)
    return state


def _user(text: str) -> ChatMessage:
    return ChatMessage(role="user", content=text)


def _ai(text: str) -> ChatMessage:
    return ChatMessage(role="assistant", content=text)


# ── BranchManager.create_branch ───────────────────────────────────────────────


class TestCreateBranch:
    def test_creates_branch_with_unique_name(self) -> None:
        state = _make_state([_user("hi"), _ai("hello")])
        bm = BranchManager(state)
        name = bm.create_branch()
        assert name == "Branch 1"  # main is 0, so first branch is 1

    def test_new_branch_copies_current_history(self) -> None:
        msgs = [_user("hi"), _ai("hello")]
        state = _make_state(msgs)
        bm = BranchManager(state)
        name = bm.create_branch()
        assert len(state.branches[name]) == 2

    def test_active_branch_changes(self) -> None:
        state = _make_state()
        bm = BranchManager(state)
        bm.create_branch()
        assert state.active_branch != "main"

    def test_branches_are_independent_after_creation(self) -> None:
        state = _make_state([_user("shared")])
        bm = BranchManager(state)
        name = bm.create_branch()
        # Add a message only to the new branch
        state.history.append(_ai("new branch reply"))
        # Switch back to main and verify it didn't receive the new message
        bm.switch_to("main")
        main_texts = [str(m.content) for m in state.history]
        assert "new branch reply" not in main_texts

    def test_sequential_branches_have_distinct_names(self) -> None:
        state = _make_state()
        bm = BranchManager(state)
        n1 = bm.create_branch()
        bm.switch_to("main")
        n2 = bm.create_branch()
        assert n1 != n2

    def test_diverge_turn_recorded(self) -> None:
        state = _make_state([_user("a"), _ai("b")])
        bm = BranchManager(state)
        name = bm.create_branch()
        assert state.branch_diverges[name] == 2


# ── BranchManager.switch_to ───────────────────────────────────────────────────


class TestSwitchTo:
    def test_switch_to_main(self) -> None:
        state = _make_state()
        bm = BranchManager(state)
        bm.create_branch()
        assert bm.switch_to("main") is True
        assert state.active_branch == "main"

    def test_switch_to_nonexistent_returns_false(self) -> None:
        state = _make_state()
        bm = BranchManager(state)
        assert bm.switch_to("Branch 99") is False

    def test_history_changes_on_switch(self) -> None:
        state = _make_state([_user("shared")])
        bm = BranchManager(state)
        branch_name = bm.create_branch()
        state.history.append(_ai("only in branch"))
        bm.switch_to("main")
        assert all(m.content != "only in branch" for m in state.history)


# ── BranchManager.list_branches ───────────────────────────────────────────────


class TestListBranches:
    def test_initial_state_has_main(self) -> None:
        state = _make_state()
        bm = BranchManager(state)
        rows = bm.list_branches()
        assert any(r["name"] == "main" for r in rows)

    def test_main_listed_first(self) -> None:
        state = _make_state()
        bm = BranchManager(state)
        bm.create_branch()
        bm.switch_to("main")
        rows = bm.list_branches()
        assert rows[0]["name"] == "main"

    def test_current_flag_is_correct(self) -> None:
        state = _make_state()
        bm = BranchManager(state)
        name = bm.create_branch()
        rows = bm.list_branches()
        current = next(r for r in rows if r["is_current"])
        assert current["name"] == name

    def test_message_count_reflects_non_system(self) -> None:
        state = _make_state([_user("hi"), _ai("hello")])
        bm = BranchManager(state)
        rows = bm.list_branches()
        main_row = next(r for r in rows if r["name"] == "main")
        assert main_row["message_count"] == 2


# ── Session persistence ────────────────────────────────────────────────────────


class TestSessionPersistence:
    def test_build_session_includes_non_main_branches(self) -> None:
        state = _make_state([_user("shared")])
        bm = BranchManager(state)
        name = bm.create_branch()
        state.history.append(_ai("branch reply"))
        session = _build_session(state)
        assert name in session.branches

    def test_main_branch_in_session_messages(self) -> None:
        state = _make_state([_user("a"), _ai("b")])
        bm = BranchManager(state)
        bm.create_branch()
        bm.switch_to("main")
        session = _build_session(state)
        assert len(session.messages) == 2

    def test_branch_round_trip(self, tmp_path: object) -> None:
        from pathlib import Path
        from anythink.session.manager import SessionManager

        sm = SessionManager(sessions_dir=Path(str(tmp_path)))
        state = _make_state([_user("q"), _ai("a")])
        bm = BranchManager(state)
        branch_name = bm.create_branch()
        state.history.append(_user("branch question"))

        session = _build_session(state)
        sm.save(session)
        loaded = sm.load(session.id)

        assert branch_name in loaded.branches
        branch = loaded.branches[branch_name]
        assert isinstance(branch, BranchInfo)

    def test_branch_diverge_turn_round_trips(self, tmp_path: object) -> None:
        from pathlib import Path
        from anythink.session.manager import SessionManager

        sm = SessionManager(sessions_dir=Path(str(tmp_path)))
        state = _make_state([_user("a"), _ai("b"), _user("c"), _ai("d")])
        bm = BranchManager(state)
        name = bm.create_branch()

        session = _build_session(state)
        sm.save(session)
        loaded = sm.load(session.id)

        assert loaded.branches[name].diverge_turn == 4


# ── Undo branch-scoping ────────────────────────────────────────────────────────


class TestUndoBranchScoping:
    def test_undo_does_not_affect_other_branches(self) -> None:
        """Truncating main does not alter Branch 1's messages."""
        state = _make_state([_user("a"), _ai("b")])
        bm = BranchManager(state)
        name = bm.create_branch()
        state.history.append(_user("c"))
        state.history.append(_ai("d"))

        bm.switch_to("main")
        # Undo on main: truncate to first message only
        state.history = state.history[:1]

        # Branch should still have its messages
        bm.switch_to(name)
        assert len(state.history) >= 2


# ── BranchInfo model ──────────────────────────────────────────────────────────


class TestBranchInfoModel:
    def test_round_trip(self) -> None:
        bi = BranchInfo(
            name="Branch 1",
            diverge_turn=3,
            messages=[ChatMessage(role="user", content="hello")],
        )
        d = bi.to_dict()
        restored = BranchInfo.from_dict(d)
        assert restored.name == "Branch 1"
        assert restored.diverge_turn == 3
        assert len(restored.messages) == 1

    def test_empty_messages_round_trip(self) -> None:
        bi = BranchInfo(name="Branch 2", diverge_turn=0)
        restored = BranchInfo.from_dict(bi.to_dict())
        assert restored.messages == []


# ── /branch command ────────────────────────────────────────────────────────────


class TestBranchCommand:
    @pytest.fixture()
    def registry(self) -> object:
        from anythink.commands.handlers import register_commands
        from anythink.commands.registry import CommandRegistry

        r = CommandRegistry()
        register_commands(r)
        return r

    @pytest.fixture()
    def ctx(self, xdg_dirs: object) -> object:
        from io import StringIO

        from anythink.app.context import AppContext

        return AppContext.create(paths=xdg_dirs, console_file=StringIO())  # type: ignore[arg-type]

    async def test_branch_list_shows_main(self, registry: object, ctx: object) -> None:
        from anythink.commands.registry import CommandRegistry
        from anythink.app.context import AppContext

        state = _make_state()
        result = await registry.dispatch("/branch list", ctx, state)  # type: ignore[union-attr]
        assert result.message is not None
        assert "main" in result.message

    async def test_branch_create_returns_confirm_action(
        self, registry: object, ctx: object
    ) -> None:
        state = _make_state()
        result = await registry.dispatch("/branch", ctx, state)  # type: ignore[union-attr]
        assert result.action == "branch_confirm"

    async def test_branch_switch_nonexistent_returns_error(
        self, registry: object, ctx: object
    ) -> None:
        state = _make_state()
        result = await registry.dispatch("/branch switch Ghost", ctx, state)  # type: ignore[union-attr]
        assert result.error is True

    async def test_branch_switch_existing_returns_action(
        self, registry: object, ctx: object
    ) -> None:
        state = _make_state()
        BranchManager(state).create_branch()
        BranchManager(state).switch_to("main")
        result = await registry.dispatch("/branch switch Branch 1", ctx, state)  # type: ignore[union-attr]
        assert result.action == "branch_switch:Branch 1"
