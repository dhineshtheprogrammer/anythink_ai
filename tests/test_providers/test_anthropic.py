"""Tests for AnthropicProvider."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from anythink.exceptions import ProviderUnavailableError
from anythink.providers.anthropic import AnthropicProvider
from anythink.providers.base import ChatMessage
from tests.test_providers.conftest import make_messages


class TestAnthropicProvider:
    def test_name(self) -> None:
        p = AnthropicProvider(api_key="sk-ant-test")
        assert p.name == "anthropic"

    def test_requires_api_key(self) -> None:
        p = AnthropicProvider(api_key="sk-ant-test")
        assert p.requires_api_key is True

    def test_supports_vision(self) -> None:
        p = AnthropicProvider()
        assert p.supports_vision is True

    def test_missing_sdk_raises(self) -> None:
        p = AnthropicProvider(api_key="sk-ant-test")
        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(ProviderUnavailableError, match="anthropic SDK not installed"):
                p._client()

    def test_build_messages_extracts_system(self) -> None:
        p = AnthropicProvider()
        messages = [
            ChatMessage(role="system", content="Be concise."),
            ChatMessage(role="user", content="Hello"),
        ]
        api_msgs, system = p._build_messages(messages)
        assert system == "Be concise."
        assert len(api_msgs) == 1
        assert api_msgs[0]["role"] == "user"

    def test_build_messages_no_system(self) -> None:
        p = AnthropicProvider()
        messages = make_messages("Hello")
        api_msgs, system = p._build_messages(messages)
        assert system is None
        assert len(api_msgs) == 1

    @pytest.mark.asyncio
    async def test_list_models_returns_known(self) -> None:
        p = AnthropicProvider()
        models = await p.list_models()
        assert any("claude" in m.id for m in models)

    @pytest.mark.asyncio
    async def test_test_connection_false_on_missing_sdk(self) -> None:
        p = AnthropicProvider(api_key="sk-ant-test")
        with patch.dict("sys.modules", {"anthropic": None}):
            result = await p.test_connection()
        assert result is False

    def test_build_messages_with_image_part(self) -> None:
        from anythink.providers.base import ChatMessage, ImagePart, TextPart

        p = AnthropicProvider()
        messages = [
            ChatMessage(
                role="user",
                content=[
                    TextPart("Look at this:"),
                    ImagePart(b"\x89PNG\r\n", "image/png"),
                ],
            ),
        ]
        api_msgs, system = p._build_messages(messages)
        assert len(api_msgs) == 1
        assert system is None
        parts = api_msgs[0]["content"]
        text_parts = [p for p in parts if p["type"] == "text"]
        image_parts = [p for p in parts if p["type"] == "image"]
        assert len(text_parts) == 1
        assert len(image_parts) == 1
        assert image_parts[0]["source"]["media_type"] == "image/png"
        assert image_parts[0]["source"]["type"] == "base64"
