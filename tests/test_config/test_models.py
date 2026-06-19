"""Tests for ModelAlias and ModelRegistry."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from anythink.config.manager import Paths
from anythink.config.models import ModelAlias, ModelRegistry
from anythink.exceptions import ConfigError


def _make_alias(alias: str = "google2", provider: str = "gemini", model_id: str = "gemini-2.0-flash") -> ModelAlias:
    return ModelAlias(alias=alias, provider=provider, model_id=model_id, context_window=1_000_000)


class TestModelAlias:
    def test_roundtrip_dict(self) -> None:
        original = _make_alias()
        restored = ModelAlias.from_dict(original.to_dict())
        assert restored.alias == original.alias
        assert restored.provider == original.provider
        assert restored.model_id == original.model_id
        assert restored.context_window == original.context_window

    def test_supports_vision_default(self) -> None:
        alias = _make_alias()
        assert alias.supports_vision is False

    def test_added_at_defaults_set(self) -> None:
        before = datetime.utcnow()
        alias = _make_alias()
        after = datetime.utcnow()
        assert before <= alias.added_at <= after


class TestModelRegistry:
    def test_empty_when_no_file(self, xdg_dirs: Paths) -> None:
        registry = ModelRegistry(xdg_dirs.models_file)
        assert registry.list_all() == []

    def test_add_and_get(self, xdg_dirs: Paths) -> None:
        registry = ModelRegistry(xdg_dirs.models_file)
        alias = _make_alias()
        registry.add(alias)
        retrieved = registry.get("google2")
        assert retrieved is not None
        assert retrieved.provider == "gemini"

    def test_add_persists_to_disk(self, xdg_dirs: Paths) -> None:
        registry = ModelRegistry(xdg_dirs.models_file)
        registry.add(_make_alias())
        # New registry instance reads from disk
        registry2 = ModelRegistry(xdg_dirs.models_file)
        assert registry2.exists("google2")

    def test_remove(self, xdg_dirs: Paths) -> None:
        registry = ModelRegistry(xdg_dirs.models_file)
        registry.add(_make_alias())
        registry.remove("google2")
        assert registry.get("google2") is None

    def test_remove_nonexistent_raises(self, xdg_dirs: Paths) -> None:
        registry = ModelRegistry(xdg_dirs.models_file)
        with pytest.raises(ConfigError):
            registry.remove("nonexistent")

    def test_list_all_sorted_by_date(self, xdg_dirs: Paths) -> None:
        registry = ModelRegistry(xdg_dirs.models_file)
        registry.add(_make_alias("first"))
        registry.add(_make_alias("second"))
        names = [a.alias for a in registry.list_all()]
        assert names == ["first", "second"]

    def test_exists_false_for_unknown(self, xdg_dirs: Paths) -> None:
        registry = ModelRegistry(xdg_dirs.models_file)
        assert registry.exists("nope") is False

    def test_get_returns_none_for_unknown(self, xdg_dirs: Paths) -> None:
        registry = ModelRegistry(xdg_dirs.models_file)
        assert registry.get("nope") is None

    def test_save_when_not_dirty_is_noop(self, xdg_dirs: Paths) -> None:
        registry = ModelRegistry(xdg_dirs.models_file)
        registry._load()  # initialise cache
        assert registry._dirty is False
        registry.save()   # should return immediately without writing
        assert not xdg_dirs.models_file.exists()

    def test_load_invalid_yaml_raises(self, xdg_dirs: Paths) -> None:
        xdg_dirs.models_file.write_text("!!bad_type")
        registry = ModelRegistry(xdg_dirs.models_file)
        with pytest.raises(ConfigError):
            registry._load()
