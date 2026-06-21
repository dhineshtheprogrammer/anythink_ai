"""Core data models and BaseProvider ABC for Anythink providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class TextPart:
    """A plain-text content part in a multimodal message."""

    text: str


@dataclass
class ImagePart:
    """A base64-encoded image content part for multimodal messages."""

    data: bytes
    mime_type: str  # "image/png", "image/jpeg", "image/webp", "image/gif"


ContentPart = TextPart | ImagePart


@dataclass
class ChatMessage:
    """A single turn in a conversation."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str | list[ContentPart]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationParams:
    """Tunable generation parameters for an LLM call.

    Providers only forward the fields they support; unsupported fields are
    silently ignored rather than causing errors.
    """

    temperature: float = 0.7
    max_tokens: int | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None  # OpenAI/Groq/Mistral only
    presence_penalty: float | None = None  # OpenAI/Groq only


@dataclass
class TokenUsage:
    """Token consumption for a single response."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class StreamChunk:
    """A single streaming token (or group of tokens) from a provider."""

    text: str
    finish_reason: str | None = None  # "stop", "length", "tool_calls", None (mid-stream)
    usage: TokenUsage | None = None  # present only in the final chunk (most providers)


@dataclass
class ModelInfo:
    """Metadata about a model available from a provider."""

    id: str
    display_name: str
    context_window: int
    supports_vision: bool = False
    supports_function_calling: bool = False


class BaseProvider(ABC):
    """Abstract base class for all LLM providers.

    Providers are pure: they never fetch API keys themselves. The caller
    (App orchestrator) passes keys at construction time.
    """

    name: str  # e.g. "groq"
    display_name: str  # e.g. "Groq"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url

    @abstractmethod
    def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        gen_params: GenerationParams | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat completion tokens as they arrive.

        Implementations are async generators, so the declared return type is
        ``AsyncIterator`` (not a coroutine). Yields StreamChunk objects; the
        final chunk has finish_reason set and may include TokenUsage.

        When ``gen_params`` is provided its fields take precedence over the
        flat ``temperature`` / ``max_tokens`` kwargs, preserving backward
        compatibility with existing callers.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Return all models available for this provider."""
        ...  # pragma: no cover

    @abstractmethod
    async def test_connection(self) -> bool:
        """Return True if the provider is reachable with the current credentials."""
        ...  # pragma: no cover

    @property
    @abstractmethod
    def supports_vision(self) -> bool:
        """True if at least some models from this provider accept image inputs."""
        ...  # pragma: no cover

    @property
    @abstractmethod
    def requires_api_key(self) -> bool:
        """False for local providers (Ollama, LM Studio, llama.cpp)."""
        ...  # pragma: no cover

    def _content_to_text(self, content: str | list[ContentPart]) -> str:
        """Extract plain text from content (ignores image parts)."""
        if isinstance(content, str):
            return content
        return " ".join(p.text for p in content if isinstance(p, TextPart))


def _resolve_params(
    gen_params: GenerationParams | None,
    temperature: float,
    max_tokens: int | None,
) -> GenerationParams:
    """Merge the two calling conventions into one GenerationParams object.

    When ``gen_params`` is supplied its fields win; the flat kwargs act as
    fallbacks so that callers that don't pass ``gen_params`` still work.
    """
    if gen_params is not None:
        return gen_params
    return GenerationParams(temperature=temperature, max_tokens=max_tokens)
