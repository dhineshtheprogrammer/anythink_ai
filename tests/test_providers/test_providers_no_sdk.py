"""SDK-agnostic tests for all providers (cohere, gemini, mistral, groq, openai).

These tests do NOT need any optional SDK installed. They verify:
- Provider metadata properties
- Lazy-import guard raises ProviderUnavailableError when SDK is missing
- Message building helpers (pure Python, no SDK calls)
- list_models() and test_connection() fallback behaviour
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from anythink.exceptions import ProviderUnavailableError
from anythink.providers.anthropic import AnthropicProvider
from anythink.providers.cohere import CohereProvider
from anythink.providers.gemini import GeminiProvider
from anythink.providers.groq import GroqProvider
from anythink.providers.lm_studio import LMStudioProvider
from anythink.providers.mistral import MistralProvider
from anythink.providers.ollama import OllamaProvider
from anythink.providers.openai import OpenAIProvider
from tests.test_providers.conftest import make_messages

# ── helpers ───────────────────────────────────────────────────────────────────


def _patch_no_sdk(module_name: str):
    return patch.dict("sys.modules", {module_name: None})


# ── Cohere ────────────────────────────────────────────────────────────────────


class TestCohereProvider:
    def test_metadata(self) -> None:
        p = CohereProvider(api_key="key")
        assert p.name == "cohere"
        assert p.display_name == "Cohere"
        assert p.requires_api_key is True
        assert p.supports_vision is False

    def test_missing_sdk_client_raises(self) -> None:
        p = CohereProvider(api_key="key")
        with _patch_no_sdk("cohere"):
            with pytest.raises(ProviderUnavailableError, match="cohere SDK not installed"):
                p._client()

    @pytest.mark.asyncio
    async def test_list_models_falls_back(self) -> None:
        p = CohereProvider(api_key="key")
        with patch.object(
            p, "_client", side_effect=ProviderUnavailableError("no sdk", provider="cohere")
        ):
            models = await p.list_models()
        assert len(models) > 0

    @pytest.mark.asyncio
    async def test_test_connection_false_on_error(self) -> None:
        p = CohereProvider(api_key="key")
        with patch.object(p, "list_models", side_effect=Exception("fail")):
            assert await p.test_connection() is False

    @pytest.mark.asyncio
    async def test_test_connection_true_on_success(self) -> None:
        p = CohereProvider(api_key="key")
        with patch.object(p, "list_models", return_value=[]):
            assert await p.test_connection() is True

    def test_build_chat_history_extracts_last_user_msg(self) -> None:
        from anythink.providers.base import ChatMessage

        p = CohereProvider(api_key="key")
        messages = [
            ChatMessage(role="user", content="First"),
            ChatMessage(role="assistant", content="Reply"),
            ChatMessage(role="user", content="Second"),
        ]
        last_msg, history = p._build_chat_history(messages)
        assert last_msg == "Second"
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_stream_chat_raises_on_missing_sdk(self) -> None:
        p = CohereProvider(api_key="key")
        with _patch_no_sdk("cohere"):
            with pytest.raises(ProviderUnavailableError, match="cohere SDK not installed"):
                async for _ in p.stream_chat(make_messages("Hi"), "command-r"):
                    pass


# ── Gemini ────────────────────────────────────────────────────────────────────


class TestGeminiProvider:
    def test_metadata(self) -> None:
        p = GeminiProvider(api_key="key")
        assert p.name == "gemini"
        assert p.display_name == "Google Gemini"
        assert p.requires_api_key is True
        assert p.supports_vision is True

    def test_missing_sdk_configure_raises(self) -> None:
        p = GeminiProvider(api_key="key")
        with (
            _patch_no_sdk("google.generativeai"),
            pytest.raises(ProviderUnavailableError, match="google-generativeai SDK not installed"),
        ):
            p._configure()

    @pytest.mark.asyncio
    async def test_list_models_falls_back(self) -> None:
        p = GeminiProvider(api_key="key")
        with patch.object(
            p, "_configure", side_effect=ProviderUnavailableError("no sdk", provider="gemini")
        ):
            models = await p.list_models()
        assert len(models) > 0

    @pytest.mark.asyncio
    async def test_test_connection_false_on_error(self) -> None:
        p = GeminiProvider(api_key="key")
        with patch.object(p, "list_models", side_effect=Exception("fail")):
            assert await p.test_connection() is False

    @pytest.mark.asyncio
    async def test_stream_chat_raises_on_missing_sdk(self) -> None:
        p = GeminiProvider(api_key="key")
        with (
            _patch_no_sdk("google.generativeai"),
            pytest.raises(ProviderUnavailableError, match="google-generativeai SDK not installed"),
        ):
            async for _ in p.stream_chat(make_messages("Hi"), "gemini-2.0-flash"):
                pass

    def test_get_system_instruction(self) -> None:
        from anythink.providers.base import ChatMessage

        p = GeminiProvider(api_key="key")
        messages = [
            ChatMessage(role="system", content="Be brief."),
            ChatMessage(role="user", content="Hi"),
        ]
        assert p._get_system_instruction(messages) == "Be brief."

    def test_get_system_instruction_none_when_absent(self) -> None:
        p = GeminiProvider(api_key="key")
        assert p._get_system_instruction(make_messages("Hi")) is None

    def test_build_contents_skips_system(self) -> None:
        from anythink.providers.base import ChatMessage

        p = GeminiProvider(api_key="key")
        messages = [ChatMessage(role="system", content="x"), ChatMessage(role="user", content="Hi")]
        contents = p._build_contents(messages)
        assert len(contents) == 1
        assert contents[0]["role"] == "user"

    def test_build_contents_with_image_and_text(self) -> None:
        from anythink.providers.base import ChatMessage, ImagePart, TextPart

        p = GeminiProvider(api_key="key")
        messages = [
            ChatMessage(role="user", content=[TextPart("Look:"), ImagePart(b"data", "image/jpeg")])
        ]
        contents = p._build_contents(messages)
        parts = contents[0]["parts"]
        assert any("text" in part for part in parts)
        assert any("inline_data" in part for part in parts)

    def test_build_contents_assistant_role(self) -> None:
        from anythink.providers.base import ChatMessage

        p = GeminiProvider(api_key="key")
        messages = [ChatMessage(role="assistant", content="Reply")]
        contents = p._build_contents(messages)
        assert contents[0]["role"] == "model"


# ── Mistral ───────────────────────────────────────────────────────────────────


class TestMistralProvider:
    def test_metadata(self) -> None:
        p = MistralProvider(api_key="key")
        assert p.name == "mistral"
        assert p.display_name == "Mistral"
        assert p.requires_api_key is True
        assert p.supports_vision is False

    def test_missing_sdk_client_raises(self) -> None:
        p = MistralProvider(api_key="key")
        with _patch_no_sdk("mistralai"):
            with pytest.raises(ProviderUnavailableError, match="mistralai SDK not installed"):
                p._client()

    @pytest.mark.asyncio
    async def test_list_models_falls_back(self) -> None:
        p = MistralProvider(api_key="key")
        with patch.object(
            p, "_client", side_effect=ProviderUnavailableError("no sdk", provider="mistral")
        ):
            models = await p.list_models()
        assert len(models) > 0

    @pytest.mark.asyncio
    async def test_test_connection_false_on_error(self) -> None:
        p = MistralProvider(api_key="key")
        with patch.object(p, "list_models", side_effect=Exception("fail")):
            assert await p.test_connection() is False

    @pytest.mark.asyncio
    async def test_stream_chat_raises_on_missing_sdk(self) -> None:
        p = MistralProvider(api_key="key")
        with _patch_no_sdk("mistralai"):
            with pytest.raises(ProviderUnavailableError, match="mistralai SDK not installed"):
                async for _ in p.stream_chat(make_messages("Hi"), "mistral-large-latest"):
                    pass

    def test_build_messages(self) -> None:
        p = MistralProvider(api_key="key")
        msgs = make_messages("Hello")
        result = p._build_messages(msgs)
        assert result[0]["content"] == "Hello"
        assert result[0]["role"] == "user"


# ── Groq (additional coverage) ────────────────────────────────────────────────


class TestGroqBuildMessages:
    def test_build_messages_plain_text(self) -> None:
        p = GroqProvider(api_key="sk-test")
        msgs = make_messages("Hello")
        result = p._build_messages(msgs)
        assert result[0] == {"role": "user", "content": "Hello"}

    def test_build_messages_multipart_extracts_text(self) -> None:
        from anythink.providers.base import ChatMessage, ImagePart, TextPart

        p = GroqProvider(api_key="sk-test")
        msg = ChatMessage(role="user", content=[TextPart("Hi"), ImagePart(b"img", "image/png")])
        result = p._build_messages([msg])
        assert "Hi" in result[0]["content"]


# ── OpenAI (additional coverage) ─────────────────────────────────────────────


class TestOpenAIBuildMessages:
    def test_build_messages_plain_text(self) -> None:
        p = OpenAIProvider(api_key="sk-test")
        result = p._build_messages(make_messages("Hello"))
        assert result[0] == {"role": "user", "content": "Hello"}

    def test_build_messages_multipart(self) -> None:
        from anythink.providers.base import ChatMessage, ImagePart, TextPart

        p = OpenAIProvider(api_key="sk-test")
        msg = ChatMessage(role="user", content=[TextPart("Hi"), ImagePart(b"\x89PNG", "image/png")])
        result = p._build_messages([msg])
        parts = result[0]["content"]
        assert any(part["type"] == "text" for part in parts)
        assert any(part["type"] == "image_url" for part in parts)


# ── All providers: instantiation without args ─────────────────────────────────


def test_all_providers_instantiate_without_args() -> None:
    """All providers must be constructable with zero arguments."""
    for cls in (
        GroqProvider,
        OpenAIProvider,
        AnthropicProvider,
        GeminiProvider,
        MistralProvider,
        CohereProvider,
        OllamaProvider,
        LMStudioProvider,
    ):
        p = cls()
        assert p.name  # non-empty string


def test_lm_studio_supports_vision() -> None:
    p = LMStudioProvider()
    assert p.supports_vision is True
