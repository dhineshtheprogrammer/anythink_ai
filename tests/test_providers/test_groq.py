"""Tests for GroqProvider (SDK mocked at client level)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.exceptions import AuthenticationError, ProviderUnavailableError, RateLimitError
from anythink.providers.groq import GroqProvider
from tests.test_providers.conftest import make_messages


def _make_chunk(text: str, finish_reason: str | None = None, usage: dict | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = text
    chunk.choices[0].finish_reason = finish_reason
    if usage:
        chunk.usage = MagicMock(
            prompt_tokens=usage["prompt"],
            completion_tokens=usage["completion"],
            total_tokens=usage["total"],
        )
    else:
        chunk.usage = None
    return chunk


async def _async_iter(items: list) -> AsyncMock:
    async def _gen():
        for item in items:
            yield item
    return _gen()


class TestGroqProvider:
    def test_requires_api_key(self) -> None:
        p = GroqProvider(api_key="sk-test")
        assert p.requires_api_key is True

    def test_supports_vision_false(self) -> None:
        p = GroqProvider(api_key="sk-test")
        assert p.supports_vision is False

    def test_missing_sdk_raises_on_client(self) -> None:
        p = GroqProvider(api_key="sk-test")
        with patch.dict("sys.modules", {"groq": None}):
            with pytest.raises(ProviderUnavailableError, match="groq SDK not installed"):
                p._client()

    @pytest.mark.asyncio
    async def test_stream_chat_raises_on_missing_sdk(self) -> None:
        """Without the groq SDK installed, stream_chat raises ProviderUnavailableError."""
        p = GroqProvider(api_key="sk-test")
        with patch.dict("sys.modules", {"groq": None}):
            with pytest.raises(ProviderUnavailableError, match="groq SDK not installed"):
                async for _ in p.stream_chat(make_messages("Hi"), "llama3-8b-8192"):
                    pass

    @pytest.mark.asyncio
    async def test_list_models_falls_back_on_error(self) -> None:
        p = GroqProvider(api_key="sk-test")
        with patch.object(p, "_client", side_effect=ProviderUnavailableError("no sdk", provider="groq")):
            models = await p.list_models()
        assert len(models) > 0

    @pytest.mark.asyncio
    async def test_test_connection_false_on_error(self) -> None:
        p = GroqProvider(api_key="sk-test")
        with patch.object(p, "list_models", side_effect=Exception("fail")):
            result = await p.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_true_on_success(self) -> None:
        p = GroqProvider(api_key="sk-test")
        with patch.object(p, "list_models", return_value=[]):
            result = await p.test_connection()
        assert result is True
