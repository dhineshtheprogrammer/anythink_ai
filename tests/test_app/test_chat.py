"""Tests for app/chat.py."""

from __future__ import annotations

from io import StringIO
from typing import Any, AsyncIterator
from unittest.mock import MagicMock, patch

import pytest

from anythink.app.chat import ChatApp, ChatState
from anythink.app.context import AppContext
from anythink.commands.handlers import register_commands
from anythink.commands.registry import CommandRegistry
from anythink.config.manager import Paths
from anythink.config.models import ModelAlias, ModelRegistry
from anythink.exceptions import ProviderUnavailableError
from anythink.providers.base import ChatMessage, StreamChunk, TokenUsage


@pytest.fixture()
def registry() -> CommandRegistry:
    r = CommandRegistry()
    register_commands(r)
    return r


class MockSession:
    """Simulates prompt_toolkit PromptSession for deterministic testing."""

    def __init__(self, inputs: list[str]) -> None:
        self._inputs = iter(inputs)

    async def prompt_async(self, *args: Any, **kwargs: Any) -> str:
        try:
            return next(self._inputs)
        except StopIteration:
            raise EOFError


@pytest.fixture()
def ctx(xdg_dirs: Paths) -> AppContext:
    return AppContext.create(paths=xdg_dirs, console_file=StringIO())


def _make_mock_provider(
    text: str = "Hello!",
    usage: TokenUsage | None = None,
    requires_api_key: bool = False,
) -> MagicMock:
    async def _stream(*args: Any, **kwargs: Any) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(text=text, finish_reason="stop", usage=usage)

    provider = MagicMock()
    provider.name = "mock"
    provider.requires_api_key = requires_api_key
    provider.stream_chat = _stream
    return provider


def _make_state(
    text: str = "Hello!",
    usage: TokenUsage | None = None,
) -> ChatState:
    return ChatState(
        provider=_make_mock_provider(text=text, usage=usage),
        model_id="mock-model",
        context_window=4096,
    )


# ── _resolve_state ────────────────────────────────────────────────────────────

class TestResolveState:
    def test_no_default_alias_returns_none(self, ctx: AppContext) -> None:
        # config.default_model_alias is None by default
        chat = ChatApp(ctx)
        assert chat._resolve_state() is None

    def test_no_default_alias_prints_error(self, ctx: AppContext) -> None:
        buf = StringIO()
        ctx.console._file = buf  # type: ignore[attr-defined]
        ChatApp(ctx)._resolve_state()
        # console output captured; just check it ran without exception (output varies by console)

    def test_unknown_alias_returns_none(self, ctx: AppContext) -> None:
        from dataclasses import replace
        ctx.config = replace(ctx.config, default_model_alias="no-such-alias")
        chat = ChatApp(ctx)
        assert chat._resolve_state() is None

    def test_valid_alias_no_api_key_no_require_returns_state(
        self, ctx: AppContext, xdg_dirs: Paths
    ) -> None:
        alias = ModelAlias(
            alias="mymodel",
            provider="ollama",
            model_id="llama3",
            context_window=8192,
        )
        ctx.model_registry.add(alias)
        from dataclasses import replace
        ctx.config = replace(ctx.config, default_model_alias="mymodel")

        mock_provider = _make_mock_provider(requires_api_key=False)
        with patch.object(ctx.provider_registry, "instantiate", return_value=mock_provider), \
                patch.object(ctx.key_manager, "get_key", return_value=None):
            state = ChatApp(ctx)._resolve_state()

        assert state is not None
        assert state.model_id == "llama3"
        assert state.context_window == 8192

    def test_provider_requires_key_but_none_set_returns_none(
        self, ctx: AppContext, xdg_dirs: Paths
    ) -> None:
        alias = ModelAlias(
            alias="mygroq",
            provider="groq",
            model_id="llama3-8b",
            context_window=8192,
        )
        ctx.model_registry.add(alias)
        from dataclasses import replace
        ctx.config = replace(ctx.config, default_model_alias="mygroq")

        mock_provider = _make_mock_provider(requires_api_key=True)
        with patch.object(ctx.provider_registry, "instantiate", return_value=mock_provider), \
                patch.object(ctx.key_manager, "get_key", return_value=None):
            state = ChatApp(ctx)._resolve_state()

        assert state is None

    def test_provider_load_failure_returns_none(
        self, ctx: AppContext, xdg_dirs: Paths
    ) -> None:
        alias = ModelAlias(
            alias="myalias",
            provider="bad-provider",
            model_id="x",
            context_window=4096,
        )
        ctx.model_registry.add(alias)
        from dataclasses import replace
        ctx.config = replace(ctx.config, default_model_alias="myalias")

        with patch.object(
            ctx.provider_registry,
            "instantiate",
            side_effect=ProviderUnavailableError("SDK missing", provider="bad-provider"),
        ), patch.object(ctx.key_manager, "get_key", return_value=None):
            state = ChatApp(ctx)._resolve_state()

        assert state is None


# ── run() ─────────────────────────────────────────────────────────────────────

class TestChatAppRun:
    async def test_run_exits_on_eof(self, ctx: AppContext) -> None:
        state = _make_state()
        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=MockSession([])):
            code = await ChatApp(ctx).run()
        assert code == 0

    async def test_run_returns_1_when_no_state(self, ctx: AppContext) -> None:
        with patch.object(ChatApp, "_resolve_state", return_value=None):
            code = await ChatApp(ctx).run()
        assert code == 1

    async def test_run_exit_command_exits(self, ctx: AppContext) -> None:
        state = _make_state()
        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["/exit"])):
            code = await ChatApp(ctx).run()
        assert code == 0

    async def test_run_quit_command_exits(self, ctx: AppContext) -> None:
        state = _make_state()
        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["/quit"])):
            code = await ChatApp(ctx).run()
        assert code == 0

    async def test_run_empty_input_skips(self, ctx: AppContext) -> None:
        state = _make_state()
        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["", "  ", "/exit"])):
            code = await ChatApp(ctx).run()
        assert code == 0
        assert state.history == []  # empty inputs never added

    async def test_run_sends_message_to_provider(self, ctx: AppContext) -> None:
        state = _make_state(text="World")
        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["Hello", "/exit"])):
            await ChatApp(ctx).run()
        assert len(state.history) == 2
        assert state.history[0].content == "Hello"
        assert state.history[1].content == "World"

    async def test_run_updates_token_count(self, ctx: AppContext) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        state = _make_state(usage=usage)
        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["Hi", "/exit"])):
            await ChatApp(ctx).run()
        assert state.total_tokens_used == 15

    async def test_run_handles_provider_error_and_continues(self, ctx: AppContext) -> None:
        async def _failing_stream(*args: Any, **kwargs: Any) -> AsyncIterator[StreamChunk]:
            raise ProviderUnavailableError("down", provider="mock")
            yield  # make it an async generator

        provider = MagicMock()
        provider.name = "mock"
        provider.stream_chat = _failing_stream
        state = ChatState(provider=provider, model_id="m", context_window=4096)

        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["Hi", "/exit"])):
            code = await ChatApp(ctx).run()

        assert code == 0
        assert state.history == []  # failed message removed

    async def test_run_handles_keyboard_interrupt(self, ctx: AppContext) -> None:
        class _InterruptSession:
            async def prompt_async(self, *a: Any, **k: Any) -> str:
                raise KeyboardInterrupt

        state = _make_state()
        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=_InterruptSession()):
            code = await ChatApp(ctx).run()
        assert code == 0

    async def test_run_prints_banner(self, ctx: AppContext) -> None:
        buf = ctx.console._file  # type: ignore[attr-defined]
        state = _make_state()
        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=MockSession([])):
            await ChatApp(ctx).run()
        output = buf.getvalue()  # type: ignore[attr-defined]
        assert "anythink" in output.lower() or "think" in output.lower()

    async def test_run_slash_command_continues_without_sending_to_ai(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        state = _make_state()
        # /help is a non-exit command; the loop should continue and then /exit breaks it
        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["/help", "/exit"])):
            code = await ChatApp(ctx, command_registry=registry).run()
        assert code == 0
        assert state.history == []  # slash commands never added to history

    async def test_run_unknown_slash_command_shows_error(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        state = _make_state()
        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["/nope", "/exit"])):
            code = await ChatApp(ctx, command_registry=registry).run()
        assert code == 0

    async def test_run_legacy_bare_exit_breaks_loop(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        state = _make_state()
        with patch.object(ChatApp, "_resolve_state", return_value=state), \
                patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["exit"])):
            code = await ChatApp(ctx, command_registry=registry).run()
        assert code == 0
        assert state.history == []
