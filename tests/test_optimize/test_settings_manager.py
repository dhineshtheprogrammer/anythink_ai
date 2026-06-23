"""Tests for optimize/settings_manager.py — OptimizeSettingsManager."""

from __future__ import annotations

from anythink.config.manager import Paths
from anythink.optimize.models import OptimizeSettings
from anythink.optimize.settings_manager import OptimizeSettingsManager


class TestOptimizeSettingsManager:
    def test_missing_file_returns_defaults(self, xdg_dirs: Paths) -> None:
        manager = OptimizeSettingsManager(path=xdg_dirs.optimize_settings_file)
        settings = manager.get()
        assert settings.enabled is True
        assert settings.mode == "auto"
        assert settings.priority == "quality"

    def test_update_persists_and_returns_new_value(self, xdg_dirs: Paths) -> None:
        manager = OptimizeSettingsManager(path=xdg_dirs.optimize_settings_file)
        updated = manager.update(enabled=False, mode="offline")
        assert updated.enabled is False
        assert updated.mode == "offline"

        # Reload from disk
        manager2 = OptimizeSettingsManager(path=xdg_dirs.optimize_settings_file)
        reloaded = manager2.get()
        assert reloaded.enabled is False
        assert reloaded.mode == "offline"

    def test_reset_returns_defaults_and_persists(self, xdg_dirs: Paths) -> None:
        manager = OptimizeSettingsManager(path=xdg_dirs.optimize_settings_file)
        manager.update(enabled=False, priority="reliability", history_max_tokens=8192)

        manager.reset()
        defaults = manager.get()
        assert defaults.enabled is True
        assert defaults.priority == "quality"
        assert defaults.history_max_tokens == 2048

        # Reload from disk to confirm persistence
        manager2 = OptimizeSettingsManager(path=xdg_dirs.optimize_settings_file)
        assert manager2.get().priority == "quality"

    def test_update_fallback_order(self, xdg_dirs: Paths) -> None:
        manager = OptimizeSettingsManager(path=xdg_dirs.optimize_settings_file)
        manager.update(fallback_order=["groq/llama3-70b", "ollama/mistral"])

        manager2 = OptimizeSettingsManager(path=xdg_dirs.optimize_settings_file)
        assert manager2.get().fallback_order == ["groq/llama3-70b", "ollama/mistral"]

    def test_update_multiple_fields_atomically(self, xdg_dirs: Paths) -> None:
        manager = OptimizeSettingsManager(path=xdg_dirs.optimize_settings_file)
        updated = manager.update(
            mode="online",
            priority="hybrid",
            ensemble_count=3,
            plan_mode_enabled=False,
        )
        assert updated.mode == "online"
        assert updated.priority == "hybrid"
        assert updated.ensemble_count == 3
        assert updated.plan_mode_enabled is False

    def test_save_is_noop_when_not_dirty(self, xdg_dirs: Paths) -> None:
        path = xdg_dirs.optimize_settings_file
        manager = OptimizeSettingsManager(path=path)
        manager.get()  # load
        # File should not exist yet (never written)
        manager.save()  # should be a no-op since _dirty is False
        assert not path.exists()

    def test_corrupt_file_falls_back_to_defaults(self, xdg_dirs: Paths) -> None:
        path = xdg_dirs.optimize_settings_file
        path.write_text("not: valid: yaml: [")

        manager = OptimizeSettingsManager(path=path)
        settings = manager.get()
        assert settings.enabled is True  # default
