"""Integration tests for AnythinkApp using Textual's run_test driver."""

from __future__ import annotations

from collections.abc import AsyncIterator
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from anythink.app.chat import ChatState
from anythink.config.schema import AppConfig
from anythink.providers.base import (
    BaseProvider,
    ChatMessage,
    ModelInfo,
    StreamChunk,
    TokenUsage,
)
from anythink.ui.bubbles import AIBubble, SystemBubble, UserBubble
from anythink.ui.textual.app import AnythinkApp
from anythink.ui.textual.conversation import ConversationView
from anythink.ui.textual.input_area import InputArea

# ── Minimal test provider ──────────────────────────────────────────────────────


class _EchoProvider(BaseProvider):
    """Provider that echoes back the last user message."""

    name = "echo"
    display_name = "Echo"

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        last = messages[-1]
        text = last.content if isinstance(last.content, str) else "..."
        yield StreamChunk(text=f"Echo: {text}", finish_reason=None)
        yield StreamChunk(
            text="",
            finish_reason="stop",
            usage=TokenUsage(5, 5, 10),
        )

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("echo-1", "Echo-1", 4096)]

    async def test_connection(self) -> bool:
        return True

    @property
    def supports_vision(self) -> bool:
        return False

    @property
    def requires_api_key(self) -> bool:
        return False


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_echo_state() -> ChatState:
    return ChatState(
        provider=_EchoProvider(),
        model_id="echo-1",
        context_window=4096,
        search_enabled=False,
    )


def _make_mock_ctx() -> object:
    """Build a MagicMock AppContext sufficient for Textual app tests."""
    from anythink.ui.theme import MIDNIGHT
    from rich.console import Console

    ctx = MagicMock()
    ctx.config = AppConfig(default_model_alias="echo-1", session_autosave=False)
    ctx.theme = MIDNIGHT
    ctx.console = Console(file=StringIO())
    ctx.search_registry = MagicMock()
    ctx.search_registry.get_available.return_value = None
    ctx.session_manager = MagicMock()
    ctx.key_manager = MagicMock()
    ctx.key_manager.get_key.return_value = None
    ctx.provider_registry = MagicMock()
    ctx.model_registry = MagicMock()
    ctx.persona_manager = MagicMock()
    return ctx


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_app_composes_core_widgets() -> None:
    """The app DOM should contain HUD, ConversationView, and InputArea."""
    ctx = _make_mock_ctx()
    state = _make_echo_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            assert tapp.query_one("#hud") is not None
            assert tapp.query_one(ConversationView) is not None
            assert tapp.query_one(InputArea) is not None


@pytest.mark.asyncio
async def test_slash_help_shows_system_bubble() -> None:
    """/help should produce a SystemBubble in the conversation."""
    ctx = _make_mock_ctx()
    state = _make_echo_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            for ch in "/help":
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause(0.3)

            conv = tapp.query_one(ConversationView)
            assert len(list(conv.query(SystemBubble))) >= 1


@pytest.mark.asyncio
async def test_user_message_creates_user_bubble() -> None:
    """Sending a plain message should create a UserBubble."""
    ctx = _make_mock_ctx()
    state = _make_echo_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            # Dismiss the session-naming prompt first (auto-name with Enter)
            await pilot.press("enter")
            await pilot.pause(0.1)
            for ch in "hello":
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause(0.1)

            conv = tapp.query_one(ConversationView)
            assert len(list(conv.query(UserBubble))) == 1


@pytest.mark.asyncio
async def test_ai_response_creates_ai_bubble() -> None:
    """After a message the streaming worker should mount an AIBubble."""
    ctx = _make_mock_ctx()
    state = _make_echo_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            # Auto-name then send message
            await pilot.press("enter")
            await pilot.pause(0.1)
            for ch in "ping":
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause(0.5)

            conv = tapp.query_one(ConversationView)
            assert len(list(conv.query(AIBubble))) == 1


@pytest.mark.asyncio
async def test_exit_command_closes_app() -> None:
    """``/exit`` should call app.exit(); the app should not error out."""
    ctx = _make_mock_ctx()
    state = _make_echo_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            for ch in "/exit":
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause(0.2)
            # After /exit the app should have exited; no exception means success


@pytest.mark.asyncio
async def test_unconfigured_shows_error_bubble() -> None:
    """When no model is configured an error SystemBubble should appear."""
    ctx = _make_mock_ctx()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=None):
        async with tapp.run_test(headless=True) as pilot:
            await pilot.pause(0.2)
            conv = tapp.query_one(ConversationView)
            error_bubbles = [b for b in conv.query(SystemBubble) if b._kind == "error"]
            assert len(error_bubbles) >= 1


@pytest.mark.asyncio
async def test_resume_prompt_shown_for_resumable_session() -> None:
    """A resumable session should trigger a resume prompt bubble."""
    from anythink.session.models import Session
    from anythink.providers.base import ChatMessage

    ctx = _make_mock_ctx()
    state = _make_echo_state()
    # Build a session that looks resumable (>= 2 non-system messages)
    resumable = Session.new("echo", "echo-1", name="My Research")
    resumable.messages = [
        ChatMessage(role="user", content="hello"),
        ChatMessage(role="assistant", content="hi there"),
    ]
    ctx.session_manager.list_sessions.return_value = [resumable]  # type: ignore[attr-defined]
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            await pilot.pause(0.2)
            conv = tapp.query_one(ConversationView)
            info_bubbles = [b for b in conv.query(SystemBubble) if b._kind == "info"]
            assert len(info_bubbles) >= 1


@pytest.mark.asyncio
async def test_resume_yes_loads_history() -> None:
    """Answering 'y' to the resume prompt should populate the state history."""
    from anythink.session.models import Session
    from anythink.providers.base import ChatMessage

    ctx = _make_mock_ctx()
    state = _make_echo_state()
    resumable = Session.new("echo", "echo-1", name="Old Session")
    resumable.messages = [
        ChatMessage(role="user", content="prior message"),
        ChatMessage(role="assistant", content="prior response"),
    ]
    ctx.session_manager.list_sessions.return_value = [resumable]  # type: ignore[attr-defined]
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            await pilot.pause(0.1)
            # Type "y" to confirm resume
            await pilot.press("y", "enter")
            await pilot.pause(0.2)
            # History should now contain the loaded messages
            assert len(tapp._state.history) == 2  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_resume_no_starts_fresh() -> None:
    """Answering 'n' should leave history empty."""
    from anythink.session.models import Session
    from anythink.providers.base import ChatMessage

    ctx = _make_mock_ctx()
    state = _make_echo_state()
    resumable = Session.new("echo", "echo-1", name="Old Session")
    resumable.messages = [
        ChatMessage(role="user", content="old"),
        ChatMessage(role="assistant", content="old reply"),
    ]
    ctx.session_manager.list_sessions.return_value = [resumable]  # type: ignore[attr-defined]
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            await pilot.pause(0.1)
            await pilot.press("n", "enter")
            await pilot.pause(0.2)
            # History should still be empty (no messages loaded)
            assert len(tapp._state.history) == 0  # type: ignore[union-attr]
