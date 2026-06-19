"""Google Gemini provider for Anythink."""

from __future__ import annotations

from typing import AsyncIterator

import httpx

from anythink.exceptions import AuthenticationError, ModelNotFoundError, ProviderUnavailableError, RateLimitError
from anythink.providers.base import BaseProvider, ChatMessage, ImagePart, ModelInfo, StreamChunk, TextPart, TokenUsage


_KNOWN_MODELS: list[ModelInfo] = [
    ModelInfo("gemini-2.0-flash", "Gemini 2.0 Flash", 1_000_000, supports_vision=True, supports_function_calling=True),
    ModelInfo("gemini-1.5-pro", "Gemini 1.5 Pro", 2_000_000, supports_vision=True, supports_function_calling=True),
    ModelInfo("gemini-1.5-flash", "Gemini 1.5 Flash", 1_000_000, supports_vision=True, supports_function_calling=True),
]


class GeminiProvider(BaseProvider):
    name = "gemini"
    display_name = "Google Gemini"

    def _configure(self) -> None:
        try:
            import google.generativeai as genai
        except ImportError:
            raise ProviderUnavailableError(
                "google-generativeai SDK not installed",
                provider=self.name,
                user_message="Install with: pip install anythink[gemini]",
            )
        genai.configure(api_key=self._api_key)

    def _get_model(self, model: str) -> "google.generativeai.GenerativeModel":
        self._configure()
        import google.generativeai as genai
        return genai.GenerativeModel(model)

    def _build_contents(self, messages: list[ChatMessage]) -> list:
        """Convert ChatMessage list to Gemini content format (skips system messages)."""
        contents = []
        for msg in messages:
            if msg.role == "system":
                continue
            role = "user" if msg.role == "user" else "model"
            if isinstance(msg.content, str):
                contents.append({"role": role, "parts": [{"text": msg.content}]})
            else:
                parts = []
                for part in msg.content:
                    if isinstance(part, TextPart):
                        parts.append({"text": part.text})
                    elif isinstance(part, ImagePart):
                        parts.append({"inline_data": {"mime_type": part.mime_type, "data": part.data}})
                contents.append({"role": role, "parts": parts})
        return contents

    def _get_system_instruction(self, messages: list[ChatMessage]) -> str | None:
        for msg in messages:
            if msg.role == "system":
                return self._content_to_text(msg.content) if isinstance(msg.content, list) else msg.content
        return None

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        try:
            import google.generativeai as genai
            import google.api_core.exceptions as gexc

            system = self._get_system_instruction(messages)
            genai_model = genai.GenerativeModel(
                model,
                system_instruction=system,
            )
            contents = self._build_contents(messages)
            gen_config = genai.GenerationConfig(
                temperature=temperature,
                **({"max_output_tokens": max_tokens} if max_tokens else {}),
            )
            response = await genai_model.generate_content_async(
                contents,
                generation_config=gen_config,
                stream=True,
            )
            total_text = ""
            async for chunk in response:
                text = chunk.text if chunk.candidates else ""
                total_text += text
                yield StreamChunk(text=text, finish_reason=None)

            usage_meta = response.usage_metadata
            if usage_meta:
                usage = TokenUsage(
                    prompt_tokens=usage_meta.prompt_token_count or 0,
                    completion_tokens=usage_meta.candidates_token_count or 0,
                    total_tokens=usage_meta.total_token_count or 0,
                )
                yield StreamChunk(text="", finish_reason="stop", usage=usage)
        except ImportError:
            raise ProviderUnavailableError(
                "google-generativeai SDK not installed",
                provider=self.name,
                user_message="Install with: pip install anythink[gemini]",
            )
        except Exception as e:
            err_str = str(e).lower()
            if "api key" in err_str or "unauthenticated" in err_str:
                raise AuthenticationError(str(e), provider=self.name) from e
            if "quota" in err_str or "rate" in err_str:
                raise RateLimitError(str(e), provider=self.name) from e
            if "not found" in err_str or "does not exist" in err_str:
                raise ModelNotFoundError(str(e), provider=self.name) from e
            raise ProviderUnavailableError(str(e), provider=self.name) from e

    async def list_models(self) -> list[ModelInfo]:
        try:
            self._configure()
            import google.generativeai as genai
            return [
                ModelInfo(
                    id=m.name.removeprefix("models/"),
                    display_name=m.display_name or m.name,
                    context_window=getattr(m, "input_token_limit", 1_000_000),
                    supports_vision=True,
                )
                async for m in await genai.list_models_async()  # type: ignore[attr-defined]
                if "generateContent" in (m.supported_generation_methods or [])
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
        return True

    @property
    def requires_api_key(self) -> bool:
        return True
