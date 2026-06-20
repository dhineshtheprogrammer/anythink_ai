"""Tests for ui/renderer.py."""

from __future__ import annotations

from collections.abc import AsyncIterator
from io import StringIO

from anythink.providers.base import StreamChunk, TokenUsage
from anythink.ui.console import make_console
from anythink.ui.renderer import StreamRenderer
from anythink.ui.theme import MIDNIGHT


async def _gen(*texts: str, usage: TokenUsage | None = None) -> AsyncIterator[StreamChunk]:
    for i, text in enumerate(texts):
        is_last = i == len(texts) - 1
        yield StreamChunk(
            text=text,
            finish_reason="stop" if is_last else None,
            usage=usage if is_last else None,
        )


def _make_renderer() -> tuple[StreamRenderer, StringIO]:
    buf = StringIO()
    console = make_console(MIDNIGHT, file=buf)
    return StreamRenderer(console=console, theme=MIDNIGHT), buf


class TestStreamRenderer:
    async def test_returns_full_text(self) -> None:
        renderer, _ = _make_renderer()
        full_text, _ = await renderer.stream(_gen("Hello", ", ", "world"))
        assert full_text == "Hello, world"

    async def test_returns_usage_from_final_chunk(self) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        renderer, _ = _make_renderer()
        _, returned_usage = await renderer.stream(_gen("hi", usage=usage))
        assert returned_usage == usage

    async def test_no_usage_when_not_provided(self) -> None:
        renderer, _ = _make_renderer()
        _, returned_usage = await renderer.stream(_gen("hi"))
        assert returned_usage is None

    async def test_empty_stream_returns_empty_string(self) -> None:
        renderer, _ = _make_renderer()

        async def _empty() -> AsyncIterator[StreamChunk]:
            return
            yield  # make it an async generator

        full_text, usage = await renderer.stream(_empty())
        assert full_text == ""
        assert usage is None

    async def test_chunk_with_no_text_does_not_appear_in_output(self) -> None:
        renderer, _ = _make_renderer()

        async def _silent() -> AsyncIterator[StreamChunk]:
            yield StreamChunk(text="", finish_reason="stop")

        full_text, _ = await renderer.stream(_silent())
        assert full_text == ""

    async def test_usage_from_chunk_without_text(self) -> None:
        usage = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        renderer, _ = _make_renderer()

        async def _usage_only() -> AsyncIterator[StreamChunk]:
            yield StreamChunk(text="word")
            yield StreamChunk(text="", finish_reason="stop", usage=usage)

        full_text, returned_usage = await renderer.stream(_usage_only())
        assert full_text == "word"
        assert returned_usage == usage

    async def test_multiple_chunks_concatenated(self) -> None:
        renderer, _ = _make_renderer()
        full_text, _ = await renderer.stream(_gen("a", "b", "c", "d"))
        assert full_text == "abcd"

    async def test_custom_refresh_rate_accepted(self) -> None:
        renderer, _ = _make_renderer()
        full_text, _ = await renderer.stream(_gen("ok"), refresh_per_second=4)
        assert full_text == "ok"
