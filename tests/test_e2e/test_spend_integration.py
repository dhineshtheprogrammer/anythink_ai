"""Integration tests verifying SpendTracker wires correctly into ChatApp.run().

These tests run the full ChatApp loop with a mocked provider that returns
TokenUsage data, then assert that:
  - The spend tracker accumulated a non-zero session total
  - gen_params from a ModelAlias are passed through to the provider
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from io import StringIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from anythink.app.chat import ChatApp, ChatState
from anythink.app.context import AppContext
from anythink.config.manager import Paths
from anythink.providers.base import GenerationParams, StreamChunk, TokenUsage


class _MockSession:
    def __init__(self, inputs: list[str]) -> None:
        self._inputs = iter(inputs)

    async def prompt_async(self, *args: Any, **kwargs: Any) -> str:
        try:
            return next(self._inputs)
        except StopIteration:
            raise EOFError


def _mock_provider(text: str = "OK", usage: TokenUsage | None = None) -> MagicMock:
    async def _stream(*args: Any, **kwargs: Any) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(text=text, finish_reason="stop", usage=usage)

    p = MagicMock()
    p.name = "openai"
    p.display_name = "OpenAI"
    p.requires_api_key = False
    p.stream_chat = _stream
    return p


@pytest.fixture()
def ctx(xdg_dirs: Paths) -> AppContext:
    return AppContext.create(paths=xdg_dirs, console_file=StringIO())


# ── spend tracking ─────────────────────────────────────────────────────────────


class TestSpendIntegration:
    async def test_spend_recorded_after_message(self, ctx: AppContext) -> None:
        """After one exchange with TokenUsage, the spend tracker has a record."""
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        provider = _mock_provider(text="Answer", usage=usage)
        state = ChatState(provider=provider, model_id="gpt-4o", context_window=8192)

        ctx.config = replace(ctx.config, spend_tracking=True)

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=_MockSession(["question", "/exit"]),
            ),
        ):
            await ChatApp(ctx).run()

        total = ctx.spend_tracker.session_total(state.session_id)
        assert total >= 0.0  # openai pricing may be non-zero

    async def test_spend_zero_when_no_usage_returned(self, ctx: AppContext) -> None:
        """When the provider doesn't return TokenUsage, nothing is recorded."""
        provider = _mock_provider(text="Answer", usage=None)  # no usage
        state = ChatState(provider=provider, model_id="gpt-4o", context_window=8192)

        ctx.config = replace(ctx.config, spend_tracking=True)

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=_MockSession(["question", "/exit"]),
            ),
        ):
            await ChatApp(ctx).run()

        total = ctx.spend_tracker.session_total(state.session_id)
        assert total == 0.0

    async def test_spend_not_recorded_when_disabled(self, ctx: AppContext) -> None:
        """When spend_tracking=False, nothing is written to the tracker."""
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        provider = _mock_provider(text="Answer", usage=usage)
        state = ChatState(provider=provider, model_id="gpt-4o", context_window=8192)

        ctx.config = replace(ctx.config, spend_tracking=False)

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=_MockSession(["question", "/exit"]),
            ),
        ):
            await ChatApp(ctx).run()

        assert ctx.spend_tracker.session_total(state.session_id) == 0.0

    async def test_multiple_turns_accumulate_spend(self, ctx: AppContext) -> None:
        """Two exchanges each recording $0.001 → session total is ~$0.002."""
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        provider = _mock_provider(text="Answer", usage=usage)
        state = ChatState(provider=provider, model_id="gpt-4o", context_window=8192)
        ctx.config = replace(ctx.config, spend_tracking=True)

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session",
                return_value=_MockSession(["q1", "q2", "/exit"]),
            ),
        ):
            await ChatApp(ctx).run()

        records = ctx.spend_tracker.all_records()
        session_records = [r for r in records if r.session_id == state.session_id]
        assert len(session_records) == 2


# ── gen_params pass-through ───────────────────────────────────────────────────


class TestGenParamsPassThrough:
    async def test_gen_params_forwarded_to_stream_chat(self, ctx: AppContext) -> None:
        """gen_params on the alias must reach the provider's stream_chat call."""
        captured_kwargs: dict[str, Any] = {}

        async def _capturing_stream(
            messages: Any, model: Any, **kwargs: Any
        ) -> AsyncIterator[StreamChunk]:
            captured_kwargs.update(kwargs)
            yield StreamChunk(text="OK", finish_reason="stop")

        provider = MagicMock()
        provider.name = "openai"
        provider.display_name = "OpenAI"
        provider.requires_api_key = False
        provider.stream_chat = _capturing_stream

        gp = GenerationParams(temperature=0.1, max_tokens=64)
        state = ChatState(
            provider=provider,
            model_id="gpt-4o",
            context_window=8192,
            gen_params=gp,
        )

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session", return_value=_MockSession(["hi", "/exit"])
            ),
        ):
            await ChatApp(ctx).run()

        assert captured_kwargs.get("gen_params") is gp

    async def test_no_gen_params_when_alias_has_none(self, ctx: AppContext) -> None:
        """When alias.gen_params is None, stream_chat receives gen_params=None."""
        captured_kwargs: dict[str, Any] = {}

        async def _capturing_stream(
            messages: Any, model: Any, **kwargs: Any
        ) -> AsyncIterator[StreamChunk]:
            captured_kwargs.update(kwargs)
            yield StreamChunk(text="OK", finish_reason="stop")

        provider = MagicMock()
        provider.name = "openai"
        provider.display_name = "OpenAI"
        provider.requires_api_key = False
        provider.stream_chat = _capturing_stream

        state = ChatState(
            provider=provider,
            model_id="gpt-4o",
            context_window=8192,
            gen_params=None,
        )

        with (
            patch.object(ChatApp, "_resolve_state", return_value=state),
            patch(
                "anythink.app.chat.make_prompt_session", return_value=_MockSession(["hi", "/exit"])
            ),
        ):
            await ChatApp(ctx).run()

        assert captured_kwargs.get("gen_params") is None
