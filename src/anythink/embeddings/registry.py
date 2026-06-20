"""EmbeddingRegistry: discovers embedding backends via entry points."""

from __future__ import annotations

from importlib.metadata import entry_points

from anythink.embeddings.base import BaseEmbeddingBackend

_ENTRY_POINT_GROUP = "anythink.embedding_backends"


class EmbeddingRegistry:
    """Mirrors SearchRegistry: discovers and caches embedding backend classes."""

    def __init__(self) -> None:
        self._backends: dict[str, BaseEmbeddingBackend] = {}

    def register(self, backend: BaseEmbeddingBackend) -> None:
        self._backends[backend.name] = backend

    def get(self, name: str) -> BaseEmbeddingBackend | None:
        return self._backends.get(name)

    def names(self) -> list[str]:
        return list(self._backends)

    def get_available(self, preferred: str | None = None) -> BaseEmbeddingBackend | None:
        """Return the preferred backend if available, else first available."""
        if preferred and (b := self._backends.get(preferred)) and b.is_available():
            return b
        return next((b for b in self._backends.values() if b.is_available()), None)

    @classmethod
    def from_entry_points(cls) -> EmbeddingRegistry:
        """Discover backends via the ``anythink.embedding_backends`` entry-point group."""
        registry = cls()
        for ep in entry_points(group=_ENTRY_POINT_GROUP):
            try:
                backend_cls = ep.load()
                backend: BaseEmbeddingBackend = backend_cls()
                registry.register(backend)
            except Exception:  # nosec B110 - skip unavailable backends
                pass
        return registry
