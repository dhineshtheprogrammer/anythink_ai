"""Provider registry: discovers providers via Python entry points."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from anythink.exceptions import PluginError

if TYPE_CHECKING:
    from anythink.providers.base import BaseProvider

_ENTRY_POINT_GROUP = "anythink.providers"


class ProviderRegistry:
    """Discovers and caches provider classes via the 'anythink.providers' entry point group."""

    def __init__(self) -> None:
        self._cache: dict[str, type[BaseProvider]] | None = None

    def _load(self) -> dict[str, type[BaseProvider]]:
        if self._cache is not None:
            return self._cache

        eps = entry_points(group=_ENTRY_POINT_GROUP)
        providers: dict[str, type[BaseProvider]] = {}
        for ep in eps:
            try:
                providers[ep.name] = ep.load()
            except Exception as exc:
                raise PluginError(
                    f"Failed to load provider '{ep.name}' from entry point '{ep.value}': {exc}",
                    user_message=f"Provider plugin '{ep.name}' failed to load. Try reinstalling it.",
                ) from exc

        self._cache = providers
        return providers

    def get(self, name: str) -> type[BaseProvider]:
        """Return the provider class for *name*. Raises PluginError if not found."""
        providers = self._load()
        if name not in providers:
            available = ", ".join(sorted(providers)) or "(none)"
            raise PluginError(
                f"Unknown provider '{name}'. Available: {available}",
                user_message=f"Provider '{name}' is not installed. Available providers: {available}",
            )
        return providers[name]

    def list_names(self) -> list[str]:
        """Return sorted list of all registered provider names."""
        return sorted(self._load())

    def instantiate(
        self,
        name: str,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> BaseProvider:
        """Instantiate a provider by name with the given credentials."""
        cls = self.get(name)
        return cls(api_key=api_key, base_url=base_url)

    def invalidate_cache(self) -> None:
        """Clear the cached provider list (useful after plugin install/remove)."""
        self._cache = None
