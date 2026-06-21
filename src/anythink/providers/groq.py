"""Groq provider for Anythink."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import httpx

from anythink.exceptions import (
    AuthenticationError,
    ModelNotFoundError,
    ProviderError,
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
    import groq as groq_sdk


_KNOWN_MODELS: list[ModelInfo] = [
    ModelInfo("llama3-8b-8192", "Llama 3 8B", 8192),
    ModelInfo("llama3-70b-8192", "Llama 3 70B", 8192),
    ModelInfo("llama-3.1-8b-instant", "Llama 3.1 8B Instant", 131072),
    ModelInfo("llama-3.1-70b-versatile", "Llama 3.1 70B Versatile", 131072),
    ModelInfo("mixtral-8x7b-32768", "Mixtral 8x7B", 32768),
    ModelInfo("gemma2-9b-it", "Gemma 2 9B IT", 8192),
]


class GroqProvider(BaseProvider):
    name = "groq"
    display_name = "Groq"

    def _client(self) -> groq_sdk.AsyncGroq:
        try:
            import groq
        except ImportError as e:
            raise ProviderUnavailableError(
                "groq SDK not installed",
                provider=self.name,
                user_message="Install with: pip install anythink[groq]",
            ) from e
        return groq.AsyncGroq(api_key=self._api_key)

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            content = (
                self._content_to_text(msg.content) if isinstance(msg.content, list) else msg.content
            )
            result.append({"role": msg.role, "content": content})
        return result

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
            "stream": True,
        }
        if params.max_tokens is not None:
            kwargs["max_tokens"] = params.max_tokens
        if params.top_p is not None:
            kwargs["top_p"] = params.top_p
        if params.frequency_penalty is not None:
            kwargs["frequency_penalty"] = params.frequency_penalty

        try:
            import groq

            stream = await client.chat.completions.create(**kwargs)
            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if choice is None:
                    continue
                delta_text = choice.delta.content or ""
                finish_reason = choice.finish_reason
                usage: TokenUsage | None = None
                if chunk.usage:
                    usage = TokenUsage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                    )
                yield StreamChunk(text=delta_text, finish_reason=finish_reason, usage=usage)
        except groq.AuthenticationError as e:
            raise AuthenticationError(str(e), provider=self.name) from e
        except groq.RateLimitError as e:
            raise RateLimitError(str(e), provider=self.name) from e
        except groq.NotFoundError as e:
            raise ModelNotFoundError(str(e), provider=self.name) from e
        except groq.APIStatusError as e:
            if e.status_code == 413:
                raise ProviderError(
                    str(e),
                    provider=self.name,
                    user_message=(
                        "Message history is too large for this model. "
                        "Use /clear to reset the conversation."
                    ),
                ) from e
            raise ProviderUnavailableError(str(e), provider=self.name) from e
        except groq.APIError as e:
            msg = str(e).lower()
            if "too large" in msg or "413" in msg or "request entity" in msg:
                raise ProviderError(
                    str(e),
                    provider=self.name,
                    user_message=(
                        "Message history is too large for this model. "
                        "Use /clear to reset the conversation."
                    ),
                ) from e
            raise ProviderUnavailableError(str(e), provider=self.name) from e
        except (groq.APIConnectionError, httpx.ConnectError) as e:
            raise ProviderUnavailableError(str(e), provider=self.name) from e

    async def list_models(self) -> list[ModelInfo]:
        try:
            client = self._client()
            response = await client.models.list()
            return [
                ModelInfo(
                    id=m.id,
                    display_name=m.id,
                    context_window=getattr(m, "context_window", 8192),
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
