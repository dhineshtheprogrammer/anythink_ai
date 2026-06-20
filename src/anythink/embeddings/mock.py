"""Mock embedding backend — deterministic, zero-dependency, for testing."""

from __future__ import annotations

import math

from anythink.embeddings.base import BaseEmbeddingBackend

_DIMS = 64


def _char_vec(text: str) -> list[float]:
    """Build a 64-dim character-frequency vector, L2-normalised."""
    vec = [0.0] * _DIMS
    for ch in text.lower():
        if ch.isalpha():
            idx = (ord(ch) - ord("a")) % _DIMS
            vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0.0:
        vec = [x / norm for x in vec]
    return vec


class MockEmbeddingBackend(BaseEmbeddingBackend):
    """Deterministic fake embeddings — always available; intended for tests."""

    name = "mock"
    display_name = "Mock (test)"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_char_vec(t) for t in texts]

    def is_available(self) -> bool:
        return True

    @property
    def dimensions(self) -> int:
        return _DIMS
