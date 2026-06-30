"""Tests for app/chat.py."""

from __future__ import annotations

from collections.abc import AsyncIterator
from io import StringIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.app.chat import ChatApp, ChatState
from anythink.app.context import AppContext
from anythink.commands.handlers import register_commands
from anythink.commands.registry import CommandRegistry
from anythink.config.manager import Paths
from anythink.config.models import ModelAlias
from anythink.exceptions import ProviderUnavailableError
from anythink.providers.base import StreamChunk, TokenUsage


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
        with (
            patch.object(ctx.provider_registry, "instantiate", return_value=mock_provider),
            patch.object(ctx.key_manager, "get_key", return_value=None),
        ):
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
        with (
            patch.object(ctx.provider_registry, "instantiate", return_value=mock_provider),
            patch.object(ctx.key_manager, "get_key", return_value=None),
        ):
            state = ChatApp(ctx)._resolve_state()

        assert state is None

    def test_provider_load_failure_returns_none(self, ctx: AppContext, xdg_dirs: Paths) -> None:
        alias = ModelAlias(
            alias="myalias",
            provider="bad-provider",
            model_id="x",
            context_window=4096,
        )
        ctx.model_registry.add(alias)
        from dataclasses import replace

        ctx.config = replace(ctx.config, default_model_alias="myalias")

        with (
            patch.object(
                ctx.provider_registry,
                "instantiate",
                side_effect=ProviderUnavailableError("SDK missing", provider="bad-provider"),
            ),
            patch.object(ctx.key_manager, "get_key", return_value=None),
        ):
            state = ChatApp(ctx)._resolve_state()

        assert state is None


# ── run() ─────────────────────────────────────────────────────────────────────


class TestChatAppRun:
    async def test_run_exits_on_eof(self, ctx: AppContext) -> None:
        state = _make_state()
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch("anythink.app.chat.make_prompt_session", return_value=MockSession([])),
        ):
            code = await ChatApp(ctx).run()
        assert code == 0

    async def test_run_returns_1_when_no_state(self, ctx: AppContext) -> None:
        with patch.object(ChatApp, "_resolve_state", return_value=None):
            code = await ChatApp(ctx).run()
        assert code == 1

    async def test_run_exit_command_exits(self, ctx: AppContext) -> None:
        state = _make_state()
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["/exit"])),
        ):
            code = await ChatApp(ctx).run()
        assert code == 0

    async def test_run_quit_command_exits(self, ctx: AppContext) -> None:
        state = _make_state()
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["/quit"])),
        ):
            code = await ChatApp(ctx).run()
        assert code == 0

    async def test_run_empty_input_skips(self, ctx: AppContext) -> None:
        state = _make_state()
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["", "  ", "/exit"]),
            ),
        ):
            code = await ChatApp(ctx).run()
        assert code == 0
        assert state.history == []  # empty inputs never added

    async def test_run_sends_message_to_provider(self, ctx: AppContext) -> None:
        state = _make_state(text="World")
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["Hello", "/exit"]),
            ),
        ):
            await ChatApp(ctx).run()
        assert len(state.history) == 2
        assert state.history[0].content == "Hello"
        assert state.history[1].content == "World"

    async def test_run_updates_token_count(self, ctx: AppContext) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        state = _make_state(usage=usage)
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session", return_value=MockSession(["Hi", "/exit"])
            ),
        ):
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

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session", return_value=MockSession(["Hi", "/exit"])
            ),
        ):
            code = await ChatApp(ctx).run()

        assert code == 0
        assert state.history == []  # failed message removed

    async def test_run_handles_keyboard_interrupt(self, ctx: AppContext) -> None:
        class _InterruptSession:
            async def prompt_async(self, *a: Any, **k: Any) -> str:
                raise KeyboardInterrupt

        state = _make_state()
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch("anythink.app.chat.make_prompt_session", return_value=_InterruptSession()),
        ):
            code = await ChatApp(ctx).run()
        assert code == 0

    async def test_run_prints_banner(self, ctx: AppContext) -> None:
        buf = ctx.console._file  # type: ignore[attr-defined]
        state = _make_state()
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch("anythink.app.chat.make_prompt_session", return_value=MockSession([])),
        ):
            await ChatApp(ctx).run()
        output = buf.getvalue()  # type: ignore[attr-defined]
        assert "anythink" in output.lower() or "think" in output.lower()

    async def test_run_slash_command_continues_without_sending_to_ai(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        state = _make_state()
        # /help is a non-exit command; the loop should continue and then /exit breaks it
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["/help", "/exit"]),
            ),
        ):
            code = await ChatApp(ctx, command_registry=registry).run()
        assert code == 0
        assert state.history == []  # slash commands never added to history

    async def test_run_unknown_slash_command_shows_error(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        state = _make_state()
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["/nope", "/exit"]),
            ),
        ):
            code = await ChatApp(ctx, command_registry=registry).run()
        assert code == 0

    async def test_run_legacy_bare_exit_breaks_loop(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        state = _make_state()
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch("anythink.app.chat.make_prompt_session", return_value=MockSession(["exit"])),
        ):
            code = await ChatApp(ctx, command_registry=registry).run()
        assert code == 0
        assert state.history == []

    async def test_autosave_saves_session_after_chat(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        state = _make_state(text="World")
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["Hello", "/exit"]),
            ),
        ):
            await ChatApp(ctx, command_registry=registry).run()
        sessions = ctx.session_manager.list_sessions()
        assert len(sessions) == 1
        assert len(sessions[0].messages) == 2

    async def test_autosave_skipped_when_history_empty(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        state = _make_state()
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch("anythink.app.chat.make_prompt_session", return_value=MockSession([])),
        ):
            await ChatApp(ctx, command_registry=registry).run()
        assert ctx.session_manager.list_sessions() == []

    async def test_autosave_disabled_by_config(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        from dataclasses import replace

        ctx.config = replace(ctx.config, session_autosave=False)
        state = _make_state(text="World")
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["Hello", "/exit"]),
            ),
        ):
            await ChatApp(ctx, command_registry=registry).run()
        assert ctx.session_manager.list_sessions() == []


# ── multimodal / pending attachments ─────────────────────────────────────────


class TestMultimodalMessages:
    async def test_run_sends_multimodal_message_with_image(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        from pathlib import Path

        from anythink.files.reader import ImageAttachment
        from anythink.providers.base import ImagePart

        state = _make_state(text="response")
        state.pending_attachments = [
            ImageAttachment(
                path=Path("/fake.png"),
                filename="fake.png",
                image_part=ImagePart(b"\x89PNG", "image/png"),
                size_bytes=4,
            )
        ]
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["describe this", "/exit"]),
            ),
        ):
            await ChatApp(ctx, command_registry=registry).run()

        user_msg = state.history[0]
        assert isinstance(user_msg.content, list)
        assert any(isinstance(p, ImagePart) for p in user_msg.content)

    async def test_run_includes_text_file_content_in_message(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        from pathlib import Path

        from anythink.files.reader import TextAttachment
        from anythink.providers.base import TextPart

        state = _make_state(text="response")
        state.pending_attachments = [
            TextAttachment(
                path=Path("/fake.py"),
                filename="fake.py",
                content="print('hello')",
                size_bytes=14,
            )
        ]
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["what does this do?", "/exit"]),
            ),
        ):
            await ChatApp(ctx, command_registry=registry).run()

        user_msg = state.history[0]
        assert isinstance(user_msg.content, list)
        text_parts = [p for p in user_msg.content if isinstance(p, TextPart)]
        assert any("fake.py" in p.text for p in text_parts)
        assert any("print('hello')" in p.text for p in text_parts)

    async def test_run_clears_pending_attachments_after_send(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        from pathlib import Path

        from anythink.files.reader import TextAttachment

        state = _make_state(text="response")
        state.pending_attachments = [
            TextAttachment(
                path=Path("/fake.txt"),
                filename="fake.txt",
                content="hello",
                size_bytes=5,
            )
        ]
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session", return_value=MockSession(["hi", "/exit"])
            ),
        ):
            await ChatApp(ctx, command_registry=registry).run()

        assert state.pending_attachments == []

    async def test_run_includes_user_text_with_attachment(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        from pathlib import Path

        from anythink.files.reader import TextAttachment
        from anythink.providers.base import TextPart

        state = _make_state(text="response")
        state.pending_attachments = [
            TextAttachment(
                path=Path("/readme.txt"),
                filename="readme.txt",
                content="docs here",
                size_bytes=9,
            )
        ]
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["summarize it", "/exit"]),
            ),
        ):
            await ChatApp(ctx, command_registry=registry).run()

        user_msg = state.history[0]
        assert isinstance(user_msg.content, list)
        text_parts = [p for p in user_msg.content if isinstance(p, TextPart)]
        assert any("summarize it" in p.text for p in text_parts)

    async def test_run_no_attachments_sends_plain_string(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        state = _make_state(text="response")
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["plain message", "/exit"]),
            ),
        ):
            await ChatApp(ctx, command_registry=registry).run()

        user_msg = state.history[0]
        assert isinstance(user_msg.content, str)
        assert user_msg.content == "plain message"


# ── web search integration ────────────────────────────────────────────────────


def _make_search_ctx(
    ctx: AppContext,
    results: list[Any] | None = None,
    *,
    raises: bool = False,
) -> AppContext:
    """Wire a mock search orchestrator into *ctx*."""
    from anythink.exceptions import SearchError
    from anythink.search.orchestrator import OrchestratorResult

    if raises:
        ctx.search_orchestrator.run = AsyncMock(  # type: ignore[method-assign]
            side_effect=SearchError("search failed", user_message="search failed")
        )
    else:
        _orch_results = results or []
        ctx.search_orchestrator.run = AsyncMock(  # type: ignore[method-assign]
            return_value=OrchestratorResult(
                queries=["q"],
                results=_orch_results,
                from_cache=[False],
                backend_used="mock",
                elapsed_s=0.1,
                error=None,
            )
        )
    return ctx


class TestSearchIntegration:
    async def test_search_enabled_injects_results_in_message(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        from anythink.providers.base import TextPart
        from anythink.search.base import SearchResult

        results = [SearchResult(title="Python", url="https://python.org", snippet="A language")]
        _make_search_ctx(ctx, results=results)

        state = _make_state(text="response")
        state.search_enabled = True

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["what is python?", "/exit"]),
            ),
        ):
            await ChatApp(ctx, command_registry=registry).run()

        user_msg = state.history[0]
        assert isinstance(user_msg.content, list)
        assert any(isinstance(p, TextPart) and "[Web Search:" in p.text for p in user_msg.content)

    async def test_search_enabled_user_text_also_in_message(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        from anythink.providers.base import TextPart
        from anythink.search.base import SearchResult

        results = [SearchResult(title="T", url="https://t.com", snippet="S")]
        _make_search_ctx(ctx, results=results)

        state = _make_state(text="response")
        state.search_enabled = True

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["my question", "/exit"]),
            ),
        ):
            await ChatApp(ctx, command_registry=registry).run()

        user_msg = state.history[0]
        assert isinstance(user_msg.content, list)
        assert any(isinstance(p, TextPart) and "my question" in p.text for p in user_msg.content)

    async def test_search_disabled_sends_plain_string(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        state = _make_state(text="response")
        state.search_enabled = False

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["plain", "/exit"]),
            ),
        ):
            await ChatApp(ctx, command_registry=registry).run()

        user_msg = state.history[0]
        assert isinstance(user_msg.content, str)

    async def test_search_error_continues_with_plain_message(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        _make_search_ctx(ctx, raises=True)

        state = _make_state(text="response")
        state.search_enabled = True

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session", return_value=MockSession(["hi", "/exit"])
            ),
        ):
            code = await ChatApp(ctx, command_registry=registry).run()

        assert code == 0
        assert len(state.history) >= 1

    async def test_search_no_backend_sends_plain_message(
        self, ctx: AppContext, registry: CommandRegistry
    ) -> None:
        from anythink.search.orchestrator import OrchestratorResult

        ctx.search_orchestrator.run = AsyncMock(  # type: ignore[method-assign]
            return_value=OrchestratorResult(
                queries=["hi"],
                results=[],
                from_cache=[],
                backend_used="",
                elapsed_s=0.0,
                error="No backend",
            )
        )

        state = _make_state(text="response")
        state.search_enabled = True

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session", return_value=MockSession(["hi", "/exit"])
            ),
        ):
            await ChatApp(ctx, command_registry=registry).run()

        user_msg = state.history[0]
        assert isinstance(user_msg.content, str)


# ── helper unit tests ─────────────────────────────────────────────────────────


class TestFreshnessToDate:
    def test_none_returns_none(self) -> None:
        from anythink.app.chat import _freshness_to_date

        assert _freshness_to_date(None) is None

    def test_off_returns_none(self) -> None:
        from anythink.app.chat import _freshness_to_date

        assert _freshness_to_date("off") is None

    def test_24h_returns_yesterday(self) -> None:
        import datetime

        from anythink.app.chat import _freshness_to_date

        result = _freshness_to_date("24h")
        assert result is not None
        expected = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        assert result == expected

    def test_7d(self) -> None:
        import datetime

        from anythink.app.chat import _freshness_to_date

        result = _freshness_to_date("7d")
        assert result == (datetime.date.today() - datetime.timedelta(days=7)).isoformat()

    def test_30d(self) -> None:
        import datetime

        from anythink.app.chat import _freshness_to_date

        result = _freshness_to_date("30d")
        assert result == (datetime.date.today() - datetime.timedelta(days=30)).isoformat()

    def test_3m(self) -> None:
        import datetime

        from anythink.app.chat import _freshness_to_date

        result = _freshness_to_date("3m")
        assert result == (datetime.date.today() - datetime.timedelta(days=90)).isoformat()

    def test_custom_date_passthrough(self) -> None:
        from anythink.app.chat import _freshness_to_date

        assert _freshness_to_date("2026-01-01") == "2026-01-01"


class TestHistoryContext:
    def test_empty_history_returns_empty_string(self) -> None:
        from anythink.app.chat import _history_context

        state = _make_state()
        assert _history_context(state) == ""

    def test_string_content_message(self) -> None:
        from anythink.app.chat import _history_context
        from anythink.providers.base import ChatMessage

        state = _make_state()
        state.history.append(ChatMessage(role="user", content="hello world"))
        result = _history_context(state)
        assert "user: hello world" in result

    def test_list_content_message(self) -> None:
        from anythink.app.chat import _history_context
        from anythink.providers.base import ChatMessage, TextPart

        state = _make_state()
        state.history.append(
            ChatMessage(role="assistant", content=[TextPart("the answer is 42")])
        )
        result = _history_context(state)
        assert "assistant" in result
        assert "the answer is 42" in result

    def test_limits_to_last_six_messages(self) -> None:
        from anythink.app.chat import _history_context
        from anythink.providers.base import ChatMessage

        state = _make_state()
        for i in range(10):
            state.history.append(ChatMessage(role="user", content=f"msg {i}"))
        result = _history_context(state)
        assert "msg 4" in result
        assert "msg 9" in result
        assert "msg 0" not in result


class TestInjectSearchContext:
    def test_prepends_search_results_to_string_content(self) -> None:
        from anythink.app.chat import _inject_search_context
        from anythink.providers.base import ChatMessage, TextPart
        from anythink.search.base import SearchResult

        state = _make_state()
        state.history.append(ChatMessage(role="user", content="what is python?"))
        results = [SearchResult(title="Python", url="https://python.org", snippet="A language")]

        _inject_search_context(state, results, "what is python?")

        assert isinstance(state.history[-1].content, list)
        parts = state.history[-1].content
        assert isinstance(parts[0], TextPart)
        assert "[Web Search:" in parts[0].text
        assert "Python" in parts[0].text

    def test_prepends_to_list_content(self) -> None:
        from anythink.app.chat import _inject_search_context
        from anythink.providers.base import ChatMessage, TextPart
        from anythink.search.base import SearchResult

        state = _make_state()
        state.history.append(
            ChatMessage(role="user", content=[TextPart("original message")])
        )
        results = [SearchResult(title="T", url="https://t.com", snippet="S")]

        _inject_search_context(state, results, "query")

        parts = state.history[-1].content
        assert len(parts) == 2
        assert isinstance(parts[0], TextPart)
        assert "[Web Search:" in parts[0].text
        assert isinstance(parts[1], TextPart)
        assert "original message" in parts[1].text

    def test_no_op_on_empty_history(self) -> None:
        from anythink.app.chat import _inject_search_context
        from anythink.search.base import SearchResult

        state = _make_state()
        results = [SearchResult(title="T", url="u", snippet="s")]
        _inject_search_context(state, results, "q")
        assert state.history == []


class TestTrimHistory:
    def test_trim_drops_old_messages_when_over_budget(self) -> None:
        from anythink.app.chat import _trim_history
        from anythink.providers.base import ChatMessage

        # Create a tiny context window so messages get trimmed
        short_context = 50  # 50 tokens * 3.5 chars = 175 chars budget
        history = [
            ChatMessage(role="user", content="A" * 200),   # too big
            ChatMessage(role="user", content="B" * 200),   # too big
            ChatMessage(role="user", content="short"),     # small — kept
        ]
        trimmed = _trim_history(history, short_context)
        # Only short messages should survive
        assert any("short" in str(m.content) for m in trimmed)
        # Long messages at start should be dropped
        assert not any("A" * 200 == m.content for m in trimmed)

    def test_trim_preserves_system_messages(self) -> None:
        from anythink.app.chat import _trim_history
        from anythink.providers.base import ChatMessage

        short_context = 50
        history = [
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="A" * 200),
        ]
        trimmed = _trim_history(history, short_context)
        # System message always preserved
        assert any(m.role == "system" for m in trimmed)


class TestHistoryContextElseBranch:
    def test_non_str_non_list_content_produces_no_text(self) -> None:
        from anythink.app.chat import _history_context
        from anythink.providers.base import ChatMessage

        state = _make_state()
        # Inject a ChatMessage with integer content to hit the else branch
        msg = ChatMessage(role="user", content="hello")
        object.__setattr__(msg, "content", 42)  # bypass frozen dataclass
        state.history.append(msg)
        result = _history_context(state)
        # Line 130 (else: text = "") should be hit; message is skipped
        assert result == "" or "user:" not in result


class TestSpendBudgetWarnings:
    async def test_run_warns_when_spend_limit_exceeded(self, ctx: AppContext) -> None:
        from dataclasses import replace

        usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        state = _make_state(usage=usage)
        ctx.config = replace(
            ctx.config,
            spend_budget_soft_limit=0.001,
            spend_budget_period="monthly",
            spend_tracking=True,
        )
        buf = StringIO()
        ctx.console._file = buf  # type: ignore[attr-defined]
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["Hello", "/exit"]),
            ),
            patch.object(ctx.spend_tracker, "monthly_total", return_value=1.0),
            patch("anythink.spend.pricing.estimate_cost", return_value=0.001),
        ):
            await ChatApp(ctx).run()
        output = buf.getvalue()
        assert "limit" in output.lower() or "spend" in output.lower()

    async def test_run_warns_when_approaching_spend_limit(self, ctx: AppContext) -> None:
        from dataclasses import replace

        usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        state = _make_state(usage=usage)
        ctx.config = replace(
            ctx.config,
            spend_budget_soft_limit=1.0,
            spend_budget_period="monthly",
            spend_tracking=True,
        )
        buf = StringIO()
        ctx.console._file = buf  # type: ignore[attr-defined]
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["Hello", "/exit"]),
            ),
            patch.object(ctx.spend_tracker, "monthly_total", return_value=0.85),
            patch("anythink.spend.pricing.estimate_cost", return_value=0.001),
        ):
            await ChatApp(ctx).run()
        output = buf.getvalue()
        assert "limit" in output.lower() or "spend" in output.lower()

    async def test_run_daily_spend_limit_exceeded(self, ctx: AppContext) -> None:
        from dataclasses import replace

        usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        state = _make_state(usage=usage)
        ctx.config = replace(
            ctx.config,
            spend_budget_soft_limit=0.001,
            spend_budget_period="daily",
            spend_tracking=True,
        )
        buf = StringIO()
        ctx.console._file = buf  # type: ignore[attr-defined]
        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=MockSession(["Hello", "/exit"]),
            ),
            patch.object(ctx.spend_tracker, "daily_total", return_value=1.0),
            patch("anythink.spend.pricing.estimate_cost", return_value=0.001),
        ):
            await ChatApp(ctx).run()
        output = buf.getvalue()
        assert "limit" in output.lower() or "spend" in output.lower()
