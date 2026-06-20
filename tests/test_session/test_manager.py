"""Tests for session/manager.py."""

from __future__ import annotations

import pytest

from anythink.config.manager import Paths
from anythink.exceptions import SessionError
from anythink.providers.base import ChatMessage
from anythink.session.manager import SessionManager
from anythink.session.models import Session


@pytest.fixture()
def sm(xdg_dirs: Paths) -> SessionManager:
    return SessionManager(sessions_dir=xdg_dirs.sessions_dir)


def _make_session(provider: str = "groq", model: str = "llama3", name: str = "") -> Session:
    s = Session.new(provider, model, name=name)
    s.messages.append(ChatMessage(role="user", content="hello"))
    return s


class TestSave:
    def test_save_creates_file(self, sm: SessionManager) -> None:
        s = _make_session()
        sm.save(s)
        assert (sm._dir / f"{s.id}.yaml").exists()

    def test_save_creates_dir_if_missing(self, xdg_dirs: Paths) -> None:
        new_dir = xdg_dirs.sessions_dir / "sub"
        sm2 = SessionManager(sessions_dir=new_dir)
        sm2.save(_make_session())
        assert new_dir.exists()

    def test_save_updates_updated_at(self, sm: SessionManager) -> None:
        s = _make_session()
        old_ts = s.updated_at
        sm.save(s)
        assert s.updated_at >= old_ts

    def test_save_overwrites_existing(self, sm: SessionManager) -> None:
        s = _make_session(name="v1")
        sm.save(s)
        s.name = "v2"
        sm.save(s)
        loaded = sm.load(s.id)
        assert loaded.name == "v2"


class TestLoad:
    def test_load_round_trips(self, sm: SessionManager) -> None:
        s = _make_session(name="test-load")
        sm.save(s)
        loaded = sm.load(s.id)
        assert loaded.id == s.id
        assert loaded.name == "test-load"
        assert len(loaded.messages) == 1

    def test_load_nonexistent_raises_session_error(self, sm: SessionManager) -> None:
        with pytest.raises(SessionError, match="not found"):
            sm.load("nonexistent-id")

    def test_load_corrupt_yaml_raises_session_error(
        self, sm: SessionManager, xdg_dirs: Paths
    ) -> None:
        path = xdg_dirs.sessions_dir / "bad.yaml"
        path.write_text("[unclosed bracket", encoding="utf-8")
        with pytest.raises(SessionError, match="Failed to parse"):
            sm.load("bad")


class TestListSessions:
    def test_list_empty_when_no_sessions(self, sm: SessionManager) -> None:
        assert sm.list_sessions() == []

    def test_list_returns_all_sessions(self, sm: SessionManager) -> None:
        sm.save(_make_session(name="a"))
        sm.save(_make_session(name="b"))
        assert len(sm.list_sessions()) == 2

    def test_list_sorted_newest_first(self, sm: SessionManager) -> None:
        import time

        s1 = _make_session(name="first")
        sm.save(s1)
        time.sleep(0.01)
        s2 = _make_session(name="second")
        sm.save(s2)
        sessions = sm.list_sessions()
        assert sessions[0].name == "second"

    def test_list_skips_corrupt_files(self, sm: SessionManager, xdg_dirs: Paths) -> None:
        sm.save(_make_session(name="good"))
        bad = xdg_dirs.sessions_dir / "bad.yaml"
        bad.write_text("not: valid: yaml: {{{", encoding="utf-8")
        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].name == "good"

    def test_list_returns_empty_when_dir_missing(self, xdg_dirs: Paths) -> None:
        sm2 = SessionManager(sessions_dir=xdg_dirs.sessions_dir / "nonexistent")
        assert sm2.list_sessions() == []


class TestDelete:
    def test_delete_removes_file(self, sm: SessionManager) -> None:
        s = _make_session()
        sm.save(s)
        sm.delete(s.id)
        assert not (sm._dir / f"{s.id}.yaml").exists()

    def test_delete_nonexistent_raises_session_error(self, sm: SessionManager) -> None:
        with pytest.raises(SessionError, match="not found"):
            sm.delete("no-such-id")

    def test_delete_not_in_list_after(self, sm: SessionManager) -> None:
        s = _make_session()
        sm.save(s)
        sm.delete(s.id)
        assert sm.list_sessions() == []


class TestBookmarkPersistence:
    def test_bookmarks_round_trip(self, sm: SessionManager) -> None:
        from anythink.bookmarks.models import Bookmark

        s = _make_session(name="bm-test")
        s.bookmarks = [Bookmark(turn_index=1, label="insight")]
        sm.save(s)
        loaded = sm.load(s.id)
        assert len(loaded.bookmarks) == 1
        assert loaded.bookmarks[0].turn_index == 1
        assert loaded.bookmarks[0].label == "insight"

    def test_no_bookmarks_round_trips_to_empty(self, sm: SessionManager) -> None:
        s = _make_session(name="no-bm")
        sm.save(s)
        loaded = sm.load(s.id)
        assert loaded.bookmarks == []


class TestFindByNameOrId:
    def test_find_by_exact_name(self, sm: SessionManager) -> None:
        s = _make_session(name="my-chat")
        sm.save(s)
        found = sm.find_by_name_or_id("my-chat")
        assert found is not None
        assert found.id == s.id

    def test_find_by_id_prefix(self, sm: SessionManager) -> None:
        s = _make_session()
        sm.save(s)
        found = sm.find_by_name_or_id(s.id[:8])
        assert found is not None
        assert found.id == s.id

    def test_find_exact_name_takes_precedence_over_id_prefix(self, sm: SessionManager) -> None:
        s1 = _make_session(name="abc12345")
        sm.save(s1)
        s2 = _make_session(name="other")
        # Give s2 an ID that starts with "abc12345" to force ambiguity
        s2.id = "abc12345-fake-id-0000-000000000000"
        sm.save(s2)
        found = sm.find_by_name_or_id("abc12345")
        assert found is not None
        assert found.id == s1.id  # name match wins

    def test_find_returns_none_when_not_found(self, sm: SessionManager) -> None:
        assert sm.find_by_name_or_id("nobody") is None
