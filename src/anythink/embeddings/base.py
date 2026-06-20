"""Base class and types for all embedding backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseEmbeddingBackend(ABC):
    """Abstract base for text-to-vector embedding backends."""

    name: str
    display_name: str

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed *texts* and return one float vector per text."""
        ...  # pragma: no cover

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if required dependencies are installed and usable."""
        ...  # pragma: no cover

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Number of dimensions in each embedding vector."""
        ...  # pragma: no cover
