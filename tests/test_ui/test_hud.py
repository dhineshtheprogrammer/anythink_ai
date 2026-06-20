"""Tests for HUDWidget — the persistent two-line heads-up display."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

import pytest

from anythink import __version__
from anythink.app.chat import ChatState
from anythink.config.schema import AppConfig
from anythink.ui.hud import HUDWidget, _context_bar
from anythink.ui.textual.app import AnythinkApp
from anythink.ui.textual.conversation import ConversationView
from anythink.ui.theme import AURORA, EMBER, MIDNIGHT

# ── _context_bar helper ────────────────────────────────────────────────────────


class TestContextBar:
    def test_green_when_below_60_pct(self) -> None:
        text = _context_bar(MIDNIGHT, 500, 1000)
        assert "█" in text.plain

    def test_zero_tokens(self) -> None:
        text = _context_bar(MIDNIGHT, 0, 1000)
        assert "░" in text.plain

    def test_all_full(self) -> None:
        text = _context_bar(MIDNIGHT, 1000, 1000)
        assert "100%" in text.plain

    def test_returns_rich_text(self) -> None:
        from rich.text import Text

        result = _context_bar(MIDNIGHT, 100, 1000)
        assert isinstance(result, Text)


# ── HUDWidget unit tests ───────────────────────────────────────────────────────


class TestHUDWidgetUnit:
    """Construction-time tests: check internal state before mounting."""

    def test_version_stored_at_construction(self) -> None:
        hud = HUDWidget(MIDNIGHT, "2.0.0")
        assert hud._version == "2.0.0"

    def test_theme_stored_at_construction(self) -> None:
        hud = HUDWidget(MIDNIGHT, "2.0.0")
        assert hud._theme.name == "midnight"

    def test_aurora_theme_stored(self) -> None:
        hud = HUDWidget(AURORA, "1.5.0")
        assert hud._theme.name == "aurora"

    def test_ember_theme_stored(self) -> None:
        hud = HUDWidget(EMBER, "1.0.0")
        assert hud._theme.name == "ember"

    def test_reactive_session_name_default_empty(self) -> None:
        # Access the reactive default directly (before mounting)
        hud = HUDWidget(MIDNIGHT, "2.0.0")
        assert hud.session_name == ""

    def test_reactive_tokens_used_default_zero(self) -> None:
        hud = HUDWidget(MIDNIGHT, "2.0.0")
        assert hud.tokens_used == 0

    def test_reactive_search_disabled_by_default(self) -> None:
        hud = HUDWidget(MIDNIGHT, "2.0.0")
        assert hud.search_enabled is False

    def test_reactive_rag_index_empty_by_default(self) -> None:
        hud = HUDWidget(MIDNIGHT, "2.0.0")
        assert hud.rag_index == ""


# ── HUD integration tests (Textual Pilot) ────────────────────────────────────


def _make_mock_ctx() -> object:
    from rich.console import Console

    ctx = MagicMock()
    ctx.config = AppConfig(
        default_model_alias="test-model",
        session_autosave=False,
        active_theme="midnight",
    )
    ctx.theme = MIDNIGHT
    ctx.console = Console(file=StringIO())
    ctx.search_registry = MagicMock()
    ctx.search_registry.get_available.return_value = None
    ctx.session_manager = MagicMock()
    ctx.session_manager.list_sessions.return_value = []
    ctx.key_manager = MagicMock()
    ctx.key_manager.get_key.return_value = None
    ctx.provider_registry = MagicMock()
    ctx.model_registry = MagicMock()
    ctx.persona_manager = MagicMock()
    return ctx


def _make_state(model_id: str = "gpt-4o") -> ChatState:
    from collections.abc import AsyncIterator
    from anythink.providers.base import BaseProvider, ModelInfo, StreamChunk

    class _FakeProvider(BaseProvider):
        name = "fake"
        display_name = "Fake"

        async def stream_chat(self, messages, model, *, max_tokens=None, temperature=0.7):  # type: ignore[override]
            yield StreamChunk(text="", finish_reason="stop")

        async def list_models(self):
            return []

        async def test_connection(self):
            return True

        @property
        def supports_vision(self):
            return False

        @property
        def requires_api_key(self):
            return False

    return ChatState(
        provider=_FakeProvider(),
        model_id=model_id,
        context_window=8192,
        search_enabled=False,
    )


@pytest.mark.asyncio
async def test_hud_present_in_dom() -> None:
    from unittest.mock import patch

    ctx = _make_mock_ctx()
    state = _make_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            hud = tapp.query_one(HUDWidget)
            assert hud is not None


@pytest.mark.asyncio
async def test_hud_shows_version() -> None:
    from unittest.mock import patch

    ctx = _make_mock_ctx()
    state = _make_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            hud = tapp.query_one(HUDWidget)
            assert hud.app_version == __version__


@pytest.mark.asyncio
async def test_hud_reflects_model_id() -> None:
    from unittest.mock import patch

    ctx = _make_mock_ctx()
    state = _make_state(model_id="gpt-4o")
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            hud = tapp.query_one(HUDWidget)
            assert hud.model_alias == "gpt-4o"


@pytest.mark.asyncio
async def test_hud_reflects_search_toggle() -> None:
    from unittest.mock import patch

    ctx = _make_mock_ctx()
    state = _make_state()
    state.search_enabled = True
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            hud = tapp.query_one(HUDWidget)
            assert hud.search_enabled is True


@pytest.mark.asyncio
async def test_hud_shows_context_window() -> None:
    from unittest.mock import patch

    ctx = _make_mock_ctx()
    state = _make_state()
    state.context_window = 16384
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            hud = tapp.query_one(HUDWidget)
            assert hud.context_window == 16384
