"""Mistral provider for Anythink."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from anythink.exceptions import (
    AuthenticationError,
    ModelNotFoundError,
    ProviderUnavailableError,
    RateLimitError,
)
from anythink.providers.base import (
    BaseProvider,
    ChatMessage,
    GenerationParams,
    ModelInfo,
    StreamChunk,
    TokenUsage,
    _resolve_params,
)

if TYPE_CHECKING:
    import mistralai

_KNOWN_MODELS: list[ModelInfo] = [
    ModelInfo("mistral-large-latest", "Mistral Large", 128_000, supports_function_calling=True),
    ModelInfo("mistral-small-latest", "Mistral Small", 128_000, supports_function_calling=True),
    ModelInfo("open-mixtral-8x22b", "Mixtral 8x22B", 65_536, supports_function_calling=True),
    ModelInfo("codestral-latest", "Codestral", 32_000),
]


class MistralProvider(BaseProvider):
    name = "mistral"
    display_name = "Mistral"

    def _client(self) -> mistralai.Mistral:
        try:
            import mistralai
        except ImportError as e:
            raise ProviderUnavailableError(
                "mistralai SDK not installed",
                provider=self.name,
                user_message="Install with: pip install anythink[mistral]",
            ) from e
        return mistralai.Mistral(api_key=self._api_key or "")

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        return [
            {
                "role": msg.role,
                "content": (
                    self._content_to_text(msg.content)
                    if isinstance(msg.content, list)
                    else msg.content
                ),
            }
            for msg in messages
        ]

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        gen_params: GenerationParams | None = None,
    ) -> AsyncIterator[StreamChunk]:
        params = _resolve_params(gen_params, temperature, max_tokens)
        client = self._client()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(messages),
            "temperature": params.temperature,
        }
        if params.max_tokens is not None:
            kwargs["max_tokens"] = params.max_tokens
        if params.top_p is not None:
            kwargs["top_p"] = params.top_p
        # Mistral does not support frequency_penalty or presence_penalty

        try:
            stream = await client.chat.stream_async(**kwargs)
            async for event in stream:
                chunk = event.data
                choice = chunk.choices[0] if chunk.choices else None
                if choice is None:
                    continue
                text = choice.delta.content or ""
                finish_reason = choice.finish_reason
                usage: TokenUsage | None = None
                if chunk.usage:
                    usage = TokenUsage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                    )
                yield StreamChunk(
                    text=text,
                    finish_reason=str(finish_reason) if finish_reason else None,
                    usage=usage,
                )
        except Exception as e:
            err = str(e).lower()
            if "401" in err or "unauthorized" in err or "api key" in err:
                raise AuthenticationError(str(e), provider=self.name) from e
            if "429" in err or "rate limit" in err:
                raise RateLimitError(str(e), provider=self.name) from e
            if "404" in err or "not found" in err:
                raise ModelNotFoundError(str(e), provider=self.name) from e
            raise ProviderUnavailableError(str(e), provider=self.name) from e

    async def list_models(self) -> list[ModelInfo]:
        try:
            client = self._client()
            response = await client.models.list_async()
            return [
                ModelInfo(
                    id=m.id,
                    display_name=m.id,
                    context_window=32_000,
                )
                for m in response.data
            ]
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
        return False

    @property
    def requires_api_key(self) -> bool:
        return True
