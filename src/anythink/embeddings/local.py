"""Local embedding backend using sentence-transformers (``pip install anythink[rag]``)."""

from __future__ import annotations

from anythink.embeddings.base import BaseEmbeddingBackend

_DEFAULT_MODEL = "all-MiniLM-L6-v2"
_DIMS = 384  # all-MiniLM-L6-v2 output dimension


class LocalEmbeddingBackend(BaseEmbeddingBackend):
    """Runs embeddings locally via sentence-transformers — no API key required."""

    name = "local"
    display_name = "Local (sentence-transformers)"

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model: object = None

    def is_available(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401

            return True
        except ImportError:
            return False

    def _load(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.is_available():
            raise ImportError("Install with: pip install anythink[rag]")
        model = self._load()
        import asyncio

        vecs = await asyncio.to_thread(model.encode, texts, convert_to_numpy=True)  # type: ignore[attr-defined]
        return [list(map(float, v)) for v in vecs]

    @property
    def dimensions(self) -> int:
        return _DIMS
