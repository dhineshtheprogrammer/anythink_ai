"""Ollama local provider for Anythink (httpx-based, no optional SDK)."""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from anythink.exceptions import ModelNotFoundError, ProviderUnavailableError
from anythink.providers.base import BaseProvider, ChatMessage, ModelInfo, StreamChunk, TokenUsage


_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider(BaseProvider):
    name = "ollama"
    display_name = "Ollama"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(api_key=api_key, base_url=base_url)
        self._url = (base_url or _DEFAULT_BASE_URL).rstrip("/")

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict]:
        return [
            {
                "role": msg.role,
                "content": self._content_to_text(msg.content) if isinstance(msg.content, list) else msg.content,
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
    ) -> AsyncIterator[StreamChunk]:
        payload: dict = {
            "model": model,
            "messages": self._build_messages(messages),
            "stream": True,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", f"{self._url}/api/chat", json=payload) as response:
                    if response.status_code == 404:
                        raise ModelNotFoundError(
                            f"Model '{model}' not found in Ollama. Pull it with: ollama pull {model}",
                            provider=self.name,
                            user_message=f"Model '{model}' not found. Run: ollama pull {model}",
                        )
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        text = data.get("message", {}).get("content", "")
                        done = data.get("done", False)
                        finish_reason = "stop" if done else None
                        usage: TokenUsage | None = None
                        if done and "prompt_eval_count" in data:
                            prompt_tok = data.get("prompt_eval_count", 0)
                            completion_tok = data.get("eval_count", 0)
                            usage = TokenUsage(
                                prompt_tokens=prompt_tok,
                                completion_tokens=completion_tok,
                                total_tokens=prompt_tok + completion_tok,
                            )
                        yield StreamChunk(text=text, finish_reason=finish_reason, usage=usage)
        except httpx.ConnectError as e:
            raise ProviderUnavailableError(
                f"Cannot connect to Ollama at {self._url}. Is Ollama running?",
                provider=self.name,
                user_message=f"Cannot reach Ollama at {self._url}. Start Ollama and try again.",
            ) from e
        except httpx.HTTPStatusError as e:
            raise ProviderUnavailableError(
                f"Ollama returned HTTP {e.response.status_code}",
                provider=self.name,
            ) from e

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self._url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return [
                    ModelInfo(
                        id=m["name"],
                        display_name=m["name"],
                        context_window=m.get("details", {}).get("context_length", 4096),
                    )
                    for m in data.get("models", [])
                ]
        except httpx.ConnectError as e:
            raise ProviderUnavailableError(
                f"Cannot connect to Ollama at {self._url}",
                provider=self.name,
                user_message=f"Cannot reach Ollama at {self._url}. Is Ollama running?",
            ) from e

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    @property
    def supports_vision(self) -> bool:
        return False

    @property
    def requires_api_key(self) -> bool:
        return False
