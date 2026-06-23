"""Tests for optimize/registry.py — ModelCapabilityRegistry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anythink.config.manager import Paths
from anythink.optimize.models import ModelCapability
from anythink.optimize.registry import ModelCapabilityRegistry


def _make_cap(model_id: str, tier: str = "free-api", strength: list[str] | None = None) -> ModelCapability:
    return ModelCapability(
        id=model_id,
        provider=model_id.split("/")[0],
        display_name=model_id,
        tier=tier,
        context_window=8192,
        max_output_tokens=4096,
        rpm_limit=30 if tier == "free-api" else None,
        tpm_limit=None,
        rpd_limit=None,
        strength_categories=strength or ["coding"],
        speed_class="fast",
        quality_class="medium",
        supports_system_prompt=True,
        supports_streaming=True,
        requires_network=tier != "local",
    )


def _write_bundled(tmp_path: Path, models: list[ModelCapability]) -> Path:
    path = tmp_path / "bundled_registry.json"
    data = {"_registry_version": "4.0.0", "models": [m.to_dict() for m in models]}
    path.write_text(json.dumps(data))
    return path


class TestModelCapabilityRegistry:
    def test_load_bundled_returns_models(self, xdg_dirs: Paths) -> None:
        """The real bundled registry (shipped with package) loads successfully."""
        reg = ModelCapabilityRegistry(
            bundled_path=None,
            user_path=xdg_dirs.model_capability_registry_user_file,
        )
        models = reg.all()
        assert len(models) > 0

    def test_bundled_contains_known_model(self, xdg_dirs: Paths) -> None:
        reg = ModelCapabilityRegistry(
            bundled_path=None,
            user_path=xdg_dirs.model_capability_registry_user_file,
        )
        cap = reg.get("groq/llama3-70b-8192")
        assert cap is not None
        assert cap.provider == "groq"
        assert cap.tier == "free-api"

    def test_user_overlay_overrides_bundled_field(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        bundled_cap = _make_cap("test/model-a", strength=["coding"])
        bundled_path = _write_bundled(tmp_path, [bundled_cap])

        # User overlay changes notes and strength_categories
        user_cap = ModelCapability(
            **{**bundled_cap.to_dict(), "notes": "USER OVERRIDE", "strength_categories": ["math"]}
        )
        user_path = xdg_dirs.model_capability_registry_user_file
        user_data = {"models": [user_cap.to_dict()]}
        user_path.write_text(json.dumps(user_data))

        reg = ModelCapabilityRegistry(bundled_path=bundled_path, user_path=user_path)
        cap = reg.get("test/model-a")
        assert cap is not None
        assert cap.notes == "USER OVERRIDE"
        assert cap.strength_categories == ["math"]

    def test_by_strength_filters_correctly(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        coding_cap = _make_cap("test/coding", strength=["coding"])
        reasoning_cap = _make_cap("test/reasoning", strength=["reasoning"])
        bundled_path = _write_bundled(tmp_path, [coding_cap, reasoning_cap])

        reg = ModelCapabilityRegistry(
            bundled_path=bundled_path,
            user_path=xdg_dirs.model_capability_registry_user_file,
        )
        coding_only = reg.by_strength("coding")
        assert any(c.id == "test/coding" for c in coding_only)
        assert not any(c.id == "test/reasoning" for c in coding_only)

    def test_available_online_returns_free_api_only(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        online = _make_cap("test/online", tier="free-api")
        offline = _make_cap("ollama/local", tier="local")
        bundled_path = _write_bundled(tmp_path, [online, offline])

        reg = ModelCapabilityRegistry(
            bundled_path=bundled_path,
            user_path=xdg_dirs.model_capability_registry_user_file,
        )
        online_models = reg.available_online()
        assert any(c.id == "test/online" for c in online_models)
        assert not any(c.id == "ollama/local" for c in online_models)

    def test_available_offline_returns_local_only(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        online = _make_cap("test/online", tier="free-api")
        offline = _make_cap("ollama/local", tier="local")
        bundled_path = _write_bundled(tmp_path, [online, offline])

        reg = ModelCapabilityRegistry(
            bundled_path=bundled_path,
            user_path=xdg_dirs.model_capability_registry_user_file,
        )
        offline_models = reg.available_offline()
        assert any(c.id == "ollama/local" for c in offline_models)
        assert not any(c.id == "test/online" for c in offline_models)

    def test_add_user_entry_persists(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        bundled_path = _write_bundled(tmp_path, [])
        user_path = xdg_dirs.model_capability_registry_user_file
        reg = ModelCapabilityRegistry(bundled_path=bundled_path, user_path=user_path)

        new_cap = _make_cap("custom/new-model")
        reg.add_user_entry(new_cap)

        # Fresh registry instance should pick up the persisted entry
        reg2 = ModelCapabilityRegistry(bundled_path=bundled_path, user_path=user_path)
        assert reg2.get("custom/new-model") is not None

    def test_remove_user_entry(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        bundled_path = _write_bundled(tmp_path, [])
        user_path = xdg_dirs.model_capability_registry_user_file
        reg = ModelCapabilityRegistry(bundled_path=bundled_path, user_path=user_path)

        cap = _make_cap("custom/to-remove")
        reg.add_user_entry(cap)
        assert reg.get("custom/to-remove") is not None

        reg.remove_user_entry("custom/to-remove")
        assert reg.get("custom/to-remove") is None

    def test_remove_nonexistent_user_entry_is_noop(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        reg = ModelCapabilityRegistry(
            bundled_path=_write_bundled(tmp_path, []),
            user_path=xdg_dirs.model_capability_registry_user_file,
        )
        reg.remove_user_entry("does/not/exist")  # should not raise

    def test_export_then_import(self, tmp_path: Path, xdg_dirs: Paths) -> None:
        cap = _make_cap("test/export-model")
        bundled_path = _write_bundled(tmp_path, [cap])
        reg = ModelCapabilityRegistry(
            bundled_path=bundled_path,
            user_path=xdg_dirs.model_capability_registry_user_file,
        )

        export_path = tmp_path / "exported.json"
        reg.export_json(export_path)

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        reg2 = ModelCapabilityRegistry(
            bundled_path=_write_bundled(empty_dir, []),
            user_path=xdg_dirs.model_capability_registry_user_file,
        )
        count = reg2.import_json(export_path)
        assert count >= 1
        assert reg2.get("test/export-model") is not None

    def test_get_nonexistent_returns_none(self, xdg_dirs: Paths) -> None:
        reg = ModelCapabilityRegistry(
            bundled_path=None,
            user_path=xdg_dirs.model_capability_registry_user_file,
        )
        assert reg.get("does-not-exist/model") is None
