"""Tests for ProviderRegistry entry-point discovery."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from anythink.exceptions import PluginError
from anythink.providers.registry import ProviderRegistry
from tests.test_providers.conftest import MockProvider


def _make_entry_point(name: str, cls: type) -> MagicMock:
    ep = MagicMock()
    ep.name = name
    ep.value = f"fake.module:{cls.__name__}"
    ep.load.return_value = cls
    return ep


class TestProviderRegistry:
    def setup_method(self) -> None:
        self.registry = ProviderRegistry()

    def _patch_eps(self, entries: list[MagicMock]) -> patch:
        return patch("anythink.providers.registry.entry_points", return_value=entries)

    def test_list_names(self) -> None:
        eps = [_make_entry_point("mock", MockProvider)]
        with self._patch_eps(eps):
            names = self.registry.list_names()
        assert names == ["mock"]

    def test_get_known_provider(self) -> None:
        eps = [_make_entry_point("mock", MockProvider)]
        with self._patch_eps(eps):
            cls = self.registry.get("mock")
        assert cls is MockProvider

    def test_get_unknown_raises_plugin_error(self) -> None:
        eps = [_make_entry_point("mock", MockProvider)]
        with self._patch_eps(eps), pytest.raises(PluginError, match="nonexistent"):
            self.registry.get("nonexistent")

    def test_instantiate(self) -> None:
        eps = [_make_entry_point("mock", MockProvider)]
        with self._patch_eps(eps):
            provider = self.registry.instantiate("mock")
        assert isinstance(provider, MockProvider)

    def test_cache_populated_after_first_call(self) -> None:
        eps = [_make_entry_point("mock", MockProvider)]
        with self._patch_eps(eps):
            self.registry.list_names()
            # Cache is set; second call should not re-invoke entry_points
            self.registry.list_names()
        assert self.registry._cache is not None

    def test_invalidate_cache(self) -> None:
        eps = [_make_entry_point("mock", MockProvider)]
        with self._patch_eps(eps):
            self.registry.list_names()
        self.registry.invalidate_cache()
        assert self.registry._cache is None

    def test_failing_entry_point_raises_plugin_error(self) -> None:
        bad_ep = MagicMock()
        bad_ep.name = "bad"
        bad_ep.value = "bad.module:BadProvider"
        bad_ep.load.side_effect = ImportError("missing dep")
        with self._patch_eps([bad_ep]):
            with pytest.raises(PluginError, match="Failed to load provider"):
                self.registry.list_names()

    def test_empty_registry_list_names(self) -> None:
        with self._patch_eps([]):
            assert self.registry.list_names() == []
