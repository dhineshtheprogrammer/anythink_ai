"""Tests for multi-model comparison runner."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import MagicMock

from anythink.compare.runner import run_comparison
from anythink.providers.base import ChatMessage, StreamChunk, TokenUsage


def _make_ctx(aliases: list[str]) -> MagicMock:
    usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)

    async def _stream(*args, **kwargs) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(text="response text", finish_reason="stop", usage=usage)

    ctx = MagicMock()

    def _get_alias(name: str) -> MagicMock | None:
        if name in aliases:
            a = MagicMock()
            a.alias = name
            a.provider = "openai"
            a.model_id = "gpt-4o"
            a.gen_params = None
            return a
        return None

    def _get_provider(**kwargs) -> MagicMock:
        p = MagicMock()
        p.name = "openai"
        p.stream_chat = _stream
        return p

    ctx.model_registry.get.side_effect = _get_alias
    ctx.model_registry.exists.side_effect = lambda n: n in aliases
    ctx.key_manager.get_key.return_value = "test-key"
    ctx.provider_registry.get.return_value = _get_provider
    return ctx


class TestRunComparison:
    async def test_returns_one_result_per_alias(self) -> None:
        ctx = _make_ctx(["alias1", "alias2"])
        messages = [ChatMessage(role="user", content="test")]
        results = await run_comparison(ctx, ["alias1", "alias2"], messages)
        assert len(results) == 2

    async def test_results_have_correct_aliases(self) -> None:
        ctx = _make_ctx(["groq-fast", "gpt4o"])
        messages = [ChatMessage(role="user", content="test")]
        results = await run_comparison(ctx, ["groq-fast", "gpt4o"], messages)
        alias_names = {r.alias for r in results}
        assert "groq-fast" in alias_names
        assert "gpt4o" in alias_names

    async def test_unknown_alias_returns_error_result(self) -> None:
        ctx = _make_ctx([])
        ctx.model_registry.get.return_value = None
        messages = [ChatMessage(role="user", content="test")]
        results = await run_comparison(ctx, ["missing-alias"], messages)
        assert len(results) == 1
        assert results[0].error is not None

    async def test_error_in_one_doesnt_abort_others(self) -> None:
        call_count = 0

        async def _stream_with_error(*args, **kwargs) -> AsyncIterator[StreamChunk]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("provider error")
            yield StreamChunk(text="ok", finish_reason="stop")

        ctx = _make_ctx(["alias1", "alias2"])

        def _get_failing_provider(**kwargs) -> MagicMock:
            p = MagicMock()
            p.name = "openai"
            p.stream_chat = _stream_with_error
            return p

        ctx.provider_registry.get.return_value = _get_failing_provider
        messages = [ChatMessage(role="user", content="test")]
        results = await run_comparison(ctx, ["alias1", "alias2"], messages)
        assert len(results) == 2
        # One should have error, one should succeed
        errors = [r for r in results if r.error]
        assert len(errors) >= 1

    async def test_cost_recorded(self) -> None:
        ctx = _make_ctx(["myalias"])
        messages = [ChatMessage(role="user", content="test")]
        results = await run_comparison(ctx, ["myalias"], messages)
        assert results[0].cost_usd >= 0.0
