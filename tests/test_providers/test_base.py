"""Tests for provider data models and BaseProvider contract."""

from __future__ import annotations

from datetime import datetime

import pytest

from anythink.providers.base import (
    ChatMessage,
    ImagePart,
    ModelInfo,
    StreamChunk,
    TextPart,
    TokenUsage,
)
from tests.test_providers.conftest import MockProvider, make_messages


class TestChatMessage:
    def test_string_content(self) -> None:
        msg = ChatMessage(role="user", content="Hello")
        assert msg.content == "Hello"
        assert msg.role == "user"

    def test_multipart_content(self) -> None:
        parts = [TextPart("hello"), ImagePart(b"\x89PNG", "image/png")]
        msg = ChatMessage(role="user", content=parts)
        assert len(msg.content) == 2  # type: ignore[arg-type]

    def test_default_timestamp_set(self) -> None:
        before = datetime.utcnow()
        msg = ChatMessage(role="assistant", content="Hi")
        after = datetime.utcnow()
        assert before <= msg.timestamp <= after

    def test_metadata_defaults_empty(self) -> None:
        msg = ChatMessage(role="user", content="x")
        assert msg.metadata == {}

    def test_roles(self) -> None:
        for role in ("user", "assistant", "system", "tool"):
            msg = ChatMessage(role=role, content="x")  # type: ignore[arg-type]
            assert msg.role == role


class TestStreamChunk:
    def test_defaults(self) -> None:
        chunk = StreamChunk(text="hello")
        assert chunk.finish_reason is None
        assert chunk.usage is None

    def test_final_chunk(self) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        chunk = StreamChunk(text="", finish_reason="stop", usage=usage)
        assert chunk.finish_reason == "stop"
        assert chunk.usage is not None
        assert chunk.usage.total_tokens == 30


class TestTokenUsage:
    def test_fields(self) -> None:
        u = TokenUsage(prompt_tokens=5, completion_tokens=10, total_tokens=15)
        assert u.total_tokens == u.prompt_tokens + u.completion_tokens


class TestModelInfo:
    def test_required_fields(self) -> None:
        m = ModelInfo(id="gpt-4o", display_name="GPT-4o", context_window=128_000)
        assert m.id == "gpt-4o"
        assert m.supports_vision is False
        assert m.supports_function_calling is False

    def test_vision_model(self) -> None:
        m = ModelInfo(id="x", display_name="X", context_window=4096, supports_vision=True)
        assert m.supports_vision is True


class TestMockProvider:
    """Verify MockProvider satisfies the BaseProvider contract."""

    @pytest.mark.asyncio
    async def test_stream_chat_yields_chunks(self) -> None:
        provider = MockProvider()
        messages = make_messages("Hello")
        chunks = [c async for c in provider.stream_chat(messages, "mock-model")]
        assert len(chunks) == 1
        assert chunks[0].text == "Hello!"

    @pytest.mark.asyncio
    async def test_list_models(self) -> None:
        provider = MockProvider()
        models = await provider.list_models()
        assert len(models) == 1
        assert models[0].id == "mock-model"

    @pytest.mark.asyncio
    async def test_test_connection(self) -> None:
        provider = MockProvider()
        assert await provider.test_connection() is True

    def test_properties(self) -> None:
        provider = MockProvider()
        assert provider.supports_vision is False
        assert provider.requires_api_key is False

    def test_records_calls(self) -> None:
        provider = MockProvider()
        msgs = make_messages("Hi")
        import asyncio

        asyncio.run(provider.stream_chat(msgs, "mock-model").__anext__())
        assert len(provider.stream_calls) == 1


class TestContentToText:
    def test_string_passthrough(self) -> None:
        provider = MockProvider()
        assert provider._content_to_text("hello") == "hello"

    def test_multipart_extracts_text(self) -> None:
        provider = MockProvider()
        parts = [TextPart("Hello "), ImagePart(b"data", "image/png"), TextPart("world")]
        assert provider._content_to_text(parts) == "Hello  world"
