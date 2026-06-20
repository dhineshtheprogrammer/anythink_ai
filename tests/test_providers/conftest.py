"""Shared fixtures for provider tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

from anythink.providers.base import BaseProvider, ChatMessage, ModelInfo, StreamChunk


def make_messages(*texts: str, role: str = "user") -> list[ChatMessage]:
    """Build a simple list of ChatMessages from strings."""
    return [ChatMessage(role=role, content=text) for text in texts]  # type: ignore[arg-type]


def make_streaming_chunks(texts: list[str], *, finish_reason: str = "stop") -> list[StreamChunk]:
    """Build a list of StreamChunks as a provider would yield them."""
    chunks = [StreamChunk(text=t) for t in texts[:-1]]
    chunks.append(StreamChunk(text=texts[-1] if texts else "", finish_reason=finish_reason))
    return chunks


class MockProvider(BaseProvider):
    """Concrete, fully controllable provider for integration tests."""

    name = "mock"
    display_name = "Mock"

    def __init__(self, chunks: list[StreamChunk] | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._chunks = chunks or [StreamChunk(text="Hello!", finish_reason="stop")]
        self.stream_calls: list[dict] = []

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        self.stream_calls.append({"messages": messages, "model": model})
        for chunk in self._chunks:
            yield chunk

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="mock-model", display_name="Mock Model", context_window=4096)]

    async def test_connection(self) -> bool:
        return True

    @property
    def supports_vision(self) -> bool:
        return False

    @property
    def requires_api_key(self) -> bool:
        return False
