"""Tests for BookmarkManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from anythink.bookmarks.manager import BookmarkManager
from anythink.bookmarks.models import Bookmark
from anythink.providers.base import ChatMessage


def _make_mgr(bookmarks: list[Bookmark] | None = None) -> BookmarkManager:
    return BookmarkManager(bookmarks or [])


class TestAdd:
    def test_add_creates_bookmark(self) -> None:
        mgr = _make_mgr()
        bm = mgr.add(4)
        assert bm.turn_index == 4
        assert bm.label == ""

    def test_add_with_label(self) -> None:
        mgr = _make_mgr()
        bm = mgr.add(2, label="key insight")
        assert bm.label == "key insight"

    def test_add_sorted_by_turn(self) -> None:
        mgr = _make_mgr()
        mgr.add(10)
        mgr.add(3)
        mgr.add(7)
        turns = [b.turn_index for b in mgr.list_all()]
        assert turns == sorted(turns)

    def test_add_replaces_existing_at_same_turn(self) -> None:
        mgr = _make_mgr()
        mgr.add(5, label="first")
        mgr.add(5, label="second")
        assert mgr.count() == 1
        assert mgr.get_by_turn(5).label == "second"  # type: ignore[union-attr]


class TestRemove:
    def test_remove_existing(self) -> None:
        mgr = _make_mgr()
        mgr.add(3)
        assert mgr.remove_by_turn(3) is True
        assert mgr.count() == 0

    def test_remove_nonexistent_returns_false(self) -> None:
        mgr = _make_mgr()
        assert mgr.remove_by_turn(99) is False


class TestLabel:
    def test_set_label_by_position(self) -> None:
        mgr = _make_mgr()
        mgr.add(2)
        assert mgr.set_label(1, "my label") is True
        assert mgr.get_by_position(1).label == "my label"  # type: ignore[union-attr]

    def test_set_label_nonexistent_returns_false(self) -> None:
        mgr = _make_mgr()
        assert mgr.set_label(5, "nope") is False


class TestQuery:
    def test_is_bookmarked_true(self) -> None:
        mgr = _make_mgr()
        mgr.add(4)
        assert mgr.is_bookmarked(4) is True

    def test_is_bookmarked_false(self) -> None:
        mgr = _make_mgr()
        assert mgr.is_bookmarked(4) is False

    def test_get_by_position_1_based(self) -> None:
        mgr = _make_mgr()
        mgr.add(0)
        mgr.add(1)
        bm = mgr.get_by_position(2)
        assert bm is not None
        assert bm.turn_index == 1

    def test_get_by_position_out_of_range_returns_none(self) -> None:
        mgr = _make_mgr()
        assert mgr.get_by_position(0) is None
        assert mgr.get_by_position(99) is None

    def test_count(self) -> None:
        mgr = _make_mgr()
        assert mgr.count() == 0
        mgr.add(0)
        mgr.add(1)
        assert mgr.count() == 2


class TestExport:
    def test_export_creates_file(self, tmp_path: Path) -> None:
        mgr = _make_mgr()
        mgr.add(1, label="key insight")
        messages = [
            ChatMessage(role="user", content="hello"),
            ChatMessage(role="assistant", content="world"),
        ]
        out = tmp_path / "export.txt"
        mgr.export_text(messages, out, session_name="test session")
        assert out.exists()

    def test_export_content_contains_label(self, tmp_path: Path) -> None:
        mgr = _make_mgr()
        mgr.add(1, label="very important")
        messages = [
            ChatMessage(role="user", content="q"),
            ChatMessage(role="assistant", content="a"),
        ]
        out = tmp_path / "bm.txt"
        mgr.export_text(messages, out)
        content = out.read_text()
        assert "very important" in content

    def test_export_skips_out_of_range_turns(self, tmp_path: Path) -> None:
        mgr = _make_mgr()
        mgr.add(999)  # far beyond message list
        out = tmp_path / "bm.txt"
        mgr.export_text([], out)
        assert out.exists()


class TestSearchSessions:
    def test_search_finds_matching_label(self) -> None:
        from datetime import datetime
        from anythink.session.models import Session

        s = Session.new("groq", "llama3", name="research")
        s.bookmarks = [Bookmark(turn_index=0, label="attention mechanism")]

        results = BookmarkManager.search_sessions([s], "attention")
        assert len(results) == 1
        assert results[0][1].label == "attention mechanism"

    def test_search_is_case_insensitive(self) -> None:
        from anythink.session.models import Session

        s = Session.new("groq", "llama3")
        s.bookmarks = [Bookmark(turn_index=0, label="BERT Insight")]
        results = BookmarkManager.search_sessions([s], "bert")
        assert len(results) == 1

    def test_search_returns_empty_when_no_match(self) -> None:
        from anythink.session.models import Session

        s = Session.new("groq", "llama3")
        s.bookmarks = [Bookmark(turn_index=0, label="GPT notes")]
        results = BookmarkManager.search_sessions([s], "transformers")
        assert results == []


class TestBookmarkModel:
    def test_round_trip(self) -> None:
        bm = Bookmark(turn_index=3, label="hello")
        restored = Bookmark.from_dict(bm.to_dict())
        assert restored.turn_index == 3
        assert restored.label == "hello"

    def test_from_dict_missing_label_defaults_to_empty(self) -> None:
        bm = Bookmark.from_dict({"turn_index": 5})
        assert bm.label == ""
        assert bm.turn_index == 5
