"""Anthropic (Claude) provider for Anythink."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, AsyncIterator

import httpx

from anythink.exceptions import AuthenticationError, ModelNotFoundError, ProviderUnavailableError, RateLimitError
from anythink.providers.base import (
    BaseProvider,
    ChatMessage,
    ImagePart,
    ModelInfo,
    StreamChunk,
    TextPart,
    TokenUsage,
)

if TYPE_CHECKING:
    import anthropic as anthropic_sdk


_KNOWN_MODELS: list[ModelInfo] = [
    ModelInfo("claude-opus-4-8", "Claude Opus 4.8", 200_000, supports_vision=True, supports_function_calling=True),
    ModelInfo("claude-sonnet-4-6", "Claude Sonnet 4.6", 200_000, supports_vision=True, supports_function_calling=True),
    ModelInfo("claude-haiku-4-5-20251001", "Claude Haiku 4.5", 200_000, supports_vision=True, supports_function_calling=True),
]


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    display_name = "Anthropic"

    def _client(self) -> "anthropic_sdk.AsyncAnthropic":
        try:
            import anthropic
        except ImportError:
            raise ProviderUnavailableError(
                "anthropic SDK not installed",
                provider=self.name,
                user_message="Install with: pip install anythink[anthropic]",
            )
        return anthropic.AsyncAnthropic(api_key=self._api_key)

    def _build_messages(self, messages: list[ChatMessage]) -> tuple[list[dict], str | None]:
        """Return (messages_list, system_prompt). Extracts system role separately."""
        system: str | None = None
        result: list[dict] = []
        for msg in messages:
            if msg.role == "system":
                system = self._content_to_text(msg.content) if isinstance(msg.content, list) else msg.content
                continue

            if isinstance(msg.content, str):
                result.append({"role": msg.role, "content": msg.content})
            else:
                parts: list[dict] = []
                for part in msg.content:
                    if isinstance(part, TextPart):
                        parts.append({"type": "text", "text": part.text})
                    elif isinstance(part, ImagePart):
                        b64 = base64.b64encode(part.data).decode()
                        parts.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": part.mime_type,
                                "data": b64,
                            },
                        })
                result.append({"role": msg.role, "content": parts})
        return result, system

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        client = self._client()
        api_messages, system = self._build_messages(messages)
        kwargs: dict = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        try:
            import anthropic
            async with client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield StreamChunk(text=text, finish_reason=None)
                final = await stream.get_final_message()
                usage = TokenUsage(
                    prompt_tokens=final.usage.input_tokens,
                    completion_tokens=final.usage.output_tokens,
                    total_tokens=final.usage.input_tokens + final.usage.output_tokens,
                )
                yield StreamChunk(text="", finish_reason=final.stop_reason, usage=usage)
        except anthropic.AuthenticationError as e:
            raise AuthenticationError(str(e), provider=self.name) from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(str(e), provider=self.name) from e
        except anthropic.NotFoundError as e:
            raise ModelNotFoundError(str(e), provider=self.name) from e
        except (anthropic.APIConnectionError, httpx.ConnectError) as e:
            raise ProviderUnavailableError(str(e), provider=self.name) from e

    async def list_models(self) -> list[ModelInfo]:
        return _KNOWN_MODELS

    async def test_connection(self) -> bool:
        try:
            client = self._client()
            import anthropic
            await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            return True
        except Exception:
            return False

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def requires_api_key(self) -> bool:
        return True
