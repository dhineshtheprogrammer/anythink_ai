"""Tests for OpenAIProvider and LMStudioProvider."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from anythink.exceptions import ProviderUnavailableError
from anythink.providers.lm_studio import LMStudioProvider
from anythink.providers.openai import OpenAIProvider


class TestOpenAIProvider:
    def test_name(self) -> None:
        p = OpenAIProvider(api_key="sk-test")
        assert p.name == "openai"
        assert p.display_name == "OpenAI"

    def test_requires_api_key(self) -> None:
        p = OpenAIProvider(api_key="sk-test")
        assert p.requires_api_key is True

    def test_supports_vision(self) -> None:
        p = OpenAIProvider()
        assert p.supports_vision is True

    def test_missing_sdk_raises(self) -> None:
        p = OpenAIProvider(api_key="sk-test")
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ProviderUnavailableError, match="openai SDK not installed"):
                p._client()

    @pytest.mark.asyncio
    async def test_list_models_falls_back(self) -> None:
        p = OpenAIProvider(api_key="sk-test")
        with patch.object(
            p, "_client", side_effect=ProviderUnavailableError("no sdk", provider="openai")
        ):
            models = await p.list_models()
        assert len(models) > 0

    @pytest.mark.asyncio
    async def test_test_connection_false_on_error(self) -> None:
        p = OpenAIProvider(api_key="sk-test")
        with patch.object(p, "list_models", side_effect=Exception("fail")):
            result = await p.test_connection()
        assert result is False


class TestLMStudioProvider:
    def test_name(self) -> None:
        p = LMStudioProvider()
        assert p.name == "lm_studio"

    def test_does_not_require_api_key(self) -> None:
        p = LMStudioProvider()
        assert p.requires_api_key is False

    def test_default_base_url(self) -> None:
        p = LMStudioProvider()
        assert "1234" in p._base_url

    def test_custom_base_url(self) -> None:
        p = LMStudioProvider(base_url="http://localhost:5678/v1")
        assert "5678" in p._base_url
