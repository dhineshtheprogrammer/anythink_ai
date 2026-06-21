"""Cohere provider for Anythink."""

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
    import cohere

_KNOWN_MODELS: list[ModelInfo] = [
    ModelInfo("command-r-plus", "Command R+", 128_000, supports_function_calling=True),
    ModelInfo("command-r", "Command R", 128_000, supports_function_calling=True),
    ModelInfo("command", "Command", 4_096),
    ModelInfo("command-light", "Command Light", 4_096),
]


class CohereProvider(BaseProvider):
    name = "cohere"
    display_name = "Cohere"

    def _client(self) -> cohere.AsyncClient:
        try:
            import cohere
        except ImportError as e:
            raise ProviderUnavailableError(
                "cohere SDK not installed",
                provider=self.name,
                user_message="Install with: pip install anythink[cohere]",
            ) from e
        return cohere.AsyncClient(api_key=self._api_key or "")

    def _build_chat_history(self, messages: list[ChatMessage]) -> tuple[str, list[dict[str, Any]]]:
        """Separate the last user message and build Cohere chat history format."""
        history: list[dict[str, Any]] = []
        last_user_msg = ""
        role_map = {"user": "USER", "assistant": "CHATBOT", "system": "SYSTEM"}

        for i, msg in enumerate(messages):
            text = (
                self._content_to_text(msg.content) if isinstance(msg.content, list) else msg.content
            )
            role = role_map.get(msg.role, "USER")
            if i == len(messages) - 1 and msg.role == "user":
                last_user_msg = text
            else:
                history.append({"role": role, "message": text})

        return last_user_msg, history

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
        message, chat_history = self._build_chat_history(messages)

        try:
            stream = client.chat_stream(
                model=model,
                message=message,
                chat_history=chat_history,
                temperature=params.temperature,
                **({"max_tokens": params.max_tokens} if params.max_tokens else {}),
                # Cohere uses p for top_p
                **({"p": params.top_p} if params.top_p is not None else {}),
                # frequency_penalty and presence_penalty not supported by Cohere
            )
            async for event in stream:
                if event.event_type == "text-generation":
                    yield StreamChunk(text=event.text, finish_reason=None)
                elif event.event_type == "stream-end":
                    usage: TokenUsage | None = None
                    if event.response and event.response.meta and event.response.meta.tokens:
                        t = event.response.meta.tokens
                        usage = TokenUsage(
                            prompt_tokens=t.input_tokens or 0,
                            completion_tokens=t.output_tokens or 0,
                            total_tokens=(t.input_tokens or 0) + (t.output_tokens or 0),
                        )
                    yield StreamChunk(text="", finish_reason="stop", usage=usage)
        except Exception as e:
            err = str(e).lower()
            if "unauthorized" in err or "api key" in err:
                raise AuthenticationError(str(e), provider=self.name) from e
            if "rate limit" in err or "429" in err:
                raise RateLimitError(str(e), provider=self.name) from e
            if "not found" in err or "404" in err:
                raise ModelNotFoundError(str(e), provider=self.name) from e
            raise ProviderUnavailableError(str(e), provider=self.name) from e

    async def list_models(self) -> list[ModelInfo]:
        try:
            client = self._client()
            response = await client.models.list()
            return [
                ModelInfo(id=m.name, display_name=m.name, context_window=m.context_length or 4_096)
                for m in (response.models or [])
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
        return False

    @property
    def requires_api_key(self) -> bool:
        return True
