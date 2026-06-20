"""OpenAI provider for Anythink (also serves as base for LM Studio)."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import httpx

from anythink.exceptions import (
    AuthenticationError,
    ModelNotFoundError,
    ProviderUnavailableError,
    RateLimitError,
)
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
    import openai as openai_sdk


_KNOWN_MODELS: list[ModelInfo] = [
    ModelInfo("gpt-4o", "GPT-4o", 128_000, supports_vision=True, supports_function_calling=True),
    ModelInfo(
        "gpt-4o-mini", "GPT-4o Mini", 128_000, supports_vision=True, supports_function_calling=True
    ),
    ModelInfo(
        "gpt-4-turbo", "GPT-4 Turbo", 128_000, supports_vision=True, supports_function_calling=True
    ),
    ModelInfo("gpt-3.5-turbo", "GPT-3.5 Turbo", 16_385, supports_function_calling=True),
]


class OpenAIProvider(BaseProvider):
    name = "openai"
    display_name = "OpenAI"

    def _client(self) -> openai_sdk.AsyncOpenAI:
        try:
            import openai
        except ImportError as e:
            raise ProviderUnavailableError(
                "openai SDK not installed",
                provider=self.name,
                user_message="Install with: pip install anythink[openai]",
            ) from e
        kwargs: dict[str, Any] = {"api_key": self._api_key or "not-needed"}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return openai.AsyncOpenAI(**kwargs)

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg.content, str):
                result.append({"role": msg.role, "content": msg.content})
            else:
                parts: list[dict[str, Any]] = []
                for part in msg.content:
                    if isinstance(part, TextPart):
                        parts.append({"type": "text", "text": part.text})
                    elif isinstance(part, ImagePart):
                        b64 = base64.b64encode(part.data).decode()
                        parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{part.mime_type};base64,{b64}"},
                            }
                        )
                result.append({"role": msg.role, "content": parts})
        return result

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        client = self._client()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            import openai

            stream = await client.chat.completions.create(**kwargs)
            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                delta_text = (choice.delta.content or "") if choice else ""
                finish_reason = choice.finish_reason if choice else None
                usage: TokenUsage | None = None
                if getattr(chunk, "usage", None):
                    usage = TokenUsage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                    )
                yield StreamChunk(text=delta_text, finish_reason=finish_reason, usage=usage)
        except openai.AuthenticationError as e:
            raise AuthenticationError(str(e), provider=self.name) from e
        except openai.RateLimitError as e:
            raise RateLimitError(str(e), provider=self.name) from e
        except openai.NotFoundError as e:
            raise ModelNotFoundError(str(e), provider=self.name) from e
        except (openai.APIConnectionError, httpx.ConnectError) as e:
            raise ProviderUnavailableError(str(e), provider=self.name) from e
        except openai.APIError as e:
            raise ProviderUnavailableError(
                str(e),
                provider=self.name,
                user_message=f"OpenAI API error: {e}",
            ) from e

    async def list_models(self) -> list[ModelInfo]:
        try:
            client = self._client()
            response = await client.models.list()
            return [
                ModelInfo(
                    id=m.id,
                    display_name=m.id,
                    context_window=128_000,
                    supports_vision="vision" in m.id or "gpt-4o" in m.id,
                )
                for m in response.data
                if m.id.startswith("gpt-")
            ] or _KNOWN_MODELS
        except Exception:
            return _KNOWN_MODELS

    async def test_connection(self) -> bool:
        try:
            await self.list_models()
            return True
        except Exception:
            return False

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def requires_api_key(self) -> bool:
        return True
