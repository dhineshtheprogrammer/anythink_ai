"""Search backend registry: discovers backends via Python entry points."""

from __future__ import annotations

from importlib.metadata import entry_points

from anythink.search.base import BaseSearchBackend

_ENTRY_POINT_GROUP = "anythink.search_backends"


class SearchRegistry:
    """Discovers and holds web search backend instances."""

    def __init__(self) -> None:
        self._backends: dict[str, BaseSearchBackend] = {}

    def register(self, backend: BaseSearchBackend) -> None:
        self._backends[backend.name] = backend

    def get(self, name: str) -> BaseSearchBackend | None:
        return self._backends.get(name)

    def names(self) -> list[str]:
        return list(self._backends)

    def get_available(self, preferred: str | None = None) -> BaseSearchBackend | None:
        """Return the preferred backend if available, else the first available one."""
        if preferred and (b := self._backends.get(preferred)) and b.is_available():
            return b
        return next((b for b in self._backends.values() if b.is_available()), None)

    @classmethod
    def from_entry_points(cls, api_keys: dict[str, str | None] | None = None) -> SearchRegistry:
        """Discover backends via the 'anythink.search_backends' entry point group."""
        registry = cls()
        keys: dict[str, str | None] = api_keys or {}
        for ep in entry_points(group=_ENTRY_POINT_GROUP):
            try:
                backend_cls = ep.load()
                backend: BaseSearchBackend = backend_cls(api_key=keys.get(ep.name))
                registry.register(backend)
            except Exception:  # nosec B110 - skip unavailable search backends
                pass
        return registry
