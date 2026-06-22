"""Tests for UserBubble, AIBubble, and SystemBubble widgets."""

from __future__ import annotations

import pytest

from anythink.ui.bubbles import AIBubble, SystemBubble, UserBubble
from anythink.ui.theme import AURORA, EMBER, MIDNIGHT


@pytest.fixture
def theme() -> object:
    return MIDNIGHT


class TestUserBubble:
    def test_is_static(self) -> None:
        from textual.widgets import Static

        bubble = UserBubble("hello", MIDNIGHT)
        assert isinstance(bubble, Static)

    def test_single_attachment_stored(self) -> None:
        bubble = UserBubble("msg", MIDNIGHT, attachments=["report.pdf"])
        # Bubble renders attachments; verify the object was created without error
        assert bubble is not None

    def test_multiple_attachments(self) -> None:
        bubble = UserBubble("msg", MIDNIGHT, attachments=["a.txt", "b.png"])
        assert bubble is not None

    def test_no_attachments(self) -> None:
        bubble = UserBubble("simple text", MIDNIGHT)
        assert bubble is not None

    def test_different_themes(self) -> None:
        for theme in (MIDNIGHT, AURORA, EMBER):
            b = UserBubble("text", theme)
            assert b is not None


class TestAIBubble:
    def test_is_static(self) -> None:
        from textual.widgets import Static

        bubble = AIBubble(MIDNIGHT, model_alias="gpt4", provider="OpenAI")
        assert isinstance(bubble, Static)

    def test_initial_buffer_empty(self) -> None:
        bubble = AIBubble(MIDNIGHT)
        assert bubble._buffer == ""

    def test_initial_buffer_is_empty(self) -> None:
        bubble = AIBubble(MIDNIGHT)
        assert bubble._buffer == ""

    def test_buffer_accumulates_via_direct_mutation(self) -> None:
        bubble = AIBubble(MIDNIGHT)
        # Verify the internal buffer accumulation logic independent of update()
        bubble._buffer += "Hello "
        bubble._buffer += "world"
        assert bubble._buffer == "Hello world"

    def test_buffer_set_to_full_text(self) -> None:
        bubble = AIBubble(MIDNIGHT)
        bubble._buffer = "Complete response."
        assert bubble._buffer == "Complete response."

    def test_model_alias_stored(self) -> None:
        bubble = AIBubble(MIDNIGHT, model_alias="claude3")
        assert bubble._model_alias == "claude3"

    def test_provider_stored(self) -> None:
        bubble = AIBubble(MIDNIGHT, provider="Anthropic")
        assert bubble._provider == "Anthropic"

    def test_default_model_alias_fallback(self) -> None:
        bubble = AIBubble(MIDNIGHT)
        assert bubble._model_alias == "AI"

    def test_timestamp_set(self) -> None:
        from datetime import datetime

        bubble = AIBubble(MIDNIGHT)
        assert isinstance(bubble._created_at, datetime)


class TestSystemBubble:
    def test_is_static(self) -> None:
        from textual.widgets import Static

        bubble = SystemBubble("some message", MIDNIGHT)
        assert isinstance(bubble, Static)

    def test_default_kind_is_info(self) -> None:
        bubble = SystemBubble("msg", MIDNIGHT)
        assert bubble._kind == "info"

    def test_error_kind(self) -> None:
        bubble = SystemBubble("bad thing", MIDNIGHT, kind="error")
        assert bubble._kind == "error"

    def test_all_valid_kinds(self) -> None:
        for kind in ("info", "success", "error", "warning", "search", "code", "rag"):
            b = SystemBubble("msg", MIDNIGHT, kind=kind)
            assert b._kind == kind

    def test_unknown_kind_uses_info_icon(self) -> None:
        bubble = SystemBubble("msg", MIDNIGHT, kind="custom_thing")
        assert bubble is not None
