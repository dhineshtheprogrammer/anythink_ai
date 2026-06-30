"""Tests for QueryRewriter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest

from anythink.search.rewriter import QueryRewriter


def _make_stream_chunk(text: str) -> MagicMock:
    chunk = MagicMock()
    chunk.text = text
    return chunk


def _make_provider(response_text: str) -> MagicMock:
    async def _gen(messages: object, model: object, **kw: object) -> AsyncIterator[MagicMock]:
        yield _make_stream_chunk(response_text)

    provider = MagicMock()
    provider.stream_chat = _gen
    return provider


def _make_error_provider(exc: Exception) -> MagicMock:
    async def _gen(messages: object, model: object, **kw: object) -> AsyncIterator[MagicMock]:
        raise exc
        yield  # make it an async generator

    provider = MagicMock()
    provider.stream_chat = _gen
    return provider


class TestQueryRewriter:
    async def test_rewrite_returns_single_line(self) -> None:
        provider = _make_provider("python async docs 2025")
        rewriter = QueryRewriter(provider, "model-id")
        result = await rewriter.rewrite("how does asyncio work in python?")
        assert result == "python async docs 2025"

    async def test_rewrite_multi_returns_multiple_lines(self) -> None:
        provider = _make_provider("python asyncio\nasyncio event loop 2025")
        rewriter = QueryRewriter(provider, "model-id")
        results = await rewriter.rewrite_multi("how does asyncio work?")
        assert len(results) == 2
        assert results[0] == "python asyncio"
        assert results[1] == "asyncio event loop 2025"

    async def test_rewrite_multi_caps_at_three(self) -> None:
        provider = _make_provider("q1\nq2\nq3\nq4\nq5")
        rewriter = QueryRewriter(provider, "model-id")
        results = await rewriter.rewrite_multi("complex question")
        assert len(results) == 3

    async def test_rewrite_falls_back_on_timeout(self) -> None:
        async def _slow_gen(messages: object, model: object, **kw: object) -> AsyncIterator[MagicMock]:
            await asyncio.sleep(10)
            yield _make_stream_chunk("never")

        provider = MagicMock()
        provider.stream_chat = _slow_gen
        rewriter = QueryRewriter(provider, "model-id")
        with patch("anythink.search.rewriter._TIMEOUT_S", 0.01):
            result = await rewriter.rewrite("original query")
        assert result == "original query"

    async def test_rewrite_falls_back_on_exception(self) -> None:
        provider = _make_error_provider(RuntimeError("LLM error"))
        rewriter = QueryRewriter(provider, "model-id")
        result = await rewriter.rewrite("my query")
        assert result == "my query"

    async def test_rewrite_multi_falls_back_on_exception(self) -> None:
        provider = _make_error_provider(Exception("oops"))
        rewriter = QueryRewriter(provider, "model-id")
        results = await rewriter.rewrite_multi("my question")
        assert results == ["my question"]

    async def test_rewrite_empty_response_falls_back(self) -> None:
        provider = _make_provider("")
        rewriter = QueryRewriter(provider, "model-id")
        result = await rewriter.rewrite("my query")
        assert result == "my query"

    async def test_history_context_included_in_message(self) -> None:
        captured_messages: list[object] = []

        async def _capture(messages: object, model: object, **kw: object) -> AsyncIterator[MagicMock]:
            if isinstance(messages, list):
                captured_messages.extend(messages)
            yield _make_stream_chunk("result query")

        provider = MagicMock()
        provider.stream_chat = _capture
        rewriter = QueryRewriter(provider, "model-id")
        await rewriter.rewrite("my question", history_context="user asked about python")
        # The user message should include the context string
        user_msgs = [m for m in captured_messages if hasattr(m, "role") and m.role == "user"]
        assert any("user asked about python" in str(getattr(m, "content", "")) for m in user_msgs)

    async def test_system_prompt_included(self) -> None:
        captured: list[object] = []

        async def _cap(messages: object, model: object, **kw: object) -> AsyncIterator[MagicMock]:
            if isinstance(messages, list):
                captured.extend(messages)
            yield _make_stream_chunk("result")

        provider = MagicMock()
        provider.stream_chat = _cap
        rewriter = QueryRewriter(provider, "model-id")
        await rewriter.rewrite("query")
        system_msgs = [m for m in captured if hasattr(m, "role") and m.role == "system"]
        assert len(system_msgs) == 1
