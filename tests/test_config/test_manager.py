"""Tests for ConfigManager and XDG path resolution."""

from __future__ import annotations

import pytest

from anythink.config.manager import ConfigManager, Paths, validate_config
from anythink.config.schema import AppConfig
from anythink.exceptions import ConfigError


class TestPaths:
    def test_config_file_path(self, xdg_dirs: Paths) -> None:
        assert xdg_dirs.config_file == xdg_dirs.config_dir / "config.yaml"

    def test_sessions_dir(self, xdg_dirs: Paths) -> None:
        assert xdg_dirs.sessions_dir == xdg_dirs.data_dir / "sessions"

    def test_ensure_dirs_creates_all(self, xdg_dirs: Paths) -> None:
        assert xdg_dirs.config_dir.exists()
        assert xdg_dirs.data_dir.exists()
        assert xdg_dirs.sessions_dir.exists()
        assert xdg_dirs.logs_dir.exists()

    def test_plugins_file_path(self, xdg_dirs: Paths) -> None:
        assert xdg_dirs.plugins_file == xdg_dirs.config_dir / "plugins.yaml"

    def test_keyring_index_file_path(self, xdg_dirs: Paths) -> None:
        assert xdg_dirs.keyring_index_file == xdg_dirs.config_dir / "keyring_index.yaml"

    def test_api_debug_log_file(self, xdg_dirs: Paths) -> None:
        assert xdg_dirs.api_debug_log_file == xdg_dirs.state_dir / "logs" / "api_debug.log"

    def test_debug_exports_dir(self, xdg_dirs: Paths) -> None:
        assert xdg_dirs.debug_exports_dir == xdg_dirs.data_dir / "debug_exports"

    def test_model_capability_registry_file(self, xdg_dirs: Paths) -> None:
        assert xdg_dirs.model_capability_registry_file == xdg_dirs.data_dir / "model_registry.json"


class TestValidateConfig:
    def test_valid_config_returns_no_errors(self) -> None:
        errors = validate_config({"active_theme": "midnight"})
        assert errors == []

    def test_invalid_theme_returns_error(self) -> None:
        errors = validate_config({"active_theme": "neon"})
        assert len(errors) == 1
        assert "neon" in str(errors[0])

    def test_invalid_warning_threshold_type(self) -> None:
        errors = validate_config({"context_warning_yellow": "high"})
        assert len(errors) == 1

    def test_out_of_range_threshold(self) -> None:
        errors = validate_config({"context_warning_red": 1.5})
        assert len(errors) == 1

    def test_multiple_errors_returned(self) -> None:
        errors = validate_config({"active_theme": "bad", "context_warning_yellow": -0.1})
        assert len(errors) == 2

    def test_valid_v2_enum_fields_no_errors(self) -> None:
        errors = validate_config(
            {
                "ui_mode": "dashboard",
                "embedding_backend": "api",
                "browse_autonomy": "auto",
                "browse_mode": "headless",
                "exec_mode": "auto",
                "voice_model": "turbo",
            }
        )
        assert errors == []

    def test_invalid_ui_mode_returns_error(self) -> None:
        errors = validate_config({"ui_mode": "fullscreen"})
        assert len(errors) == 1
        assert "ui_mode" in str(errors[0])

    def test_invalid_voice_model_returns_error(self) -> None:
        errors = validate_config({"voice_model": "gigantic"})
        assert len(errors) == 1
        assert "voice_model" in str(errors[0])

    def test_new_themes_pass_validation(self) -> None:
        for name in ("charcoal", "linen", "rose", "dracula"):
            errors = validate_config({"active_theme": name})
            assert errors == [], f"Theme '{name}' should be valid but got: {errors}"

    def test_search_max_per_response_out_of_range(self) -> None:
        errors = validate_config({"search_max_per_response": 0})
        assert any("search_max_per_response" in str(e) for e in errors)

    def test_search_max_per_response_too_high(self) -> None:
        errors = validate_config({"search_max_per_response": 25})
        assert any("search_max_per_response" in str(e) for e in errors)

    def test_search_max_per_response_non_integer(self) -> None:
        errors = validate_config({"search_max_per_response": "not-a-number"})
        assert any("search_max_per_response" in str(e) for e in errors)

    def test_search_cache_ttl_minutes_out_of_range(self) -> None:
        errors = validate_config({"search_cache_ttl_minutes": 0})
        assert any("search_cache_ttl_minutes" in str(e) for e in errors)

    def test_search_cache_ttl_minutes_non_integer(self) -> None:
        errors = validate_config({"search_cache_ttl_minutes": "bad"})
        assert any("search_cache_ttl_minutes" in str(e) for e in errors)

    def test_search_preview_delay_out_of_range(self) -> None:
        errors = validate_config({"search_preview_delay_s": 31.0})
        assert any("search_preview_delay_s" in str(e) for e in errors)

    def test_search_preview_delay_non_numeric(self) -> None:
        errors = validate_config({"search_preview_delay_s": "fast"})
        assert any("search_preview_delay_s" in str(e) for e in errors)

    def test_windows_screenshot_max_px_invalid(self) -> None:
        errors = validate_config({"windows_screenshot_max_px": "big"})
        assert any("windows_screenshot_max_px" in str(e) for e in errors)

    def test_windows_screenshot_max_px_negative(self) -> None:
        errors = validate_config({"windows_screenshot_max_px": -1})
        assert any("windows_screenshot_max_px" in str(e) for e in errors)


class TestConfigManager:
    def test_is_configured_false_when_no_file(self, config_manager: ConfigManager) -> None:
        assert config_manager.is_configured() is False

    def test_load_returns_defaults_when_no_file(self, config_manager: ConfigManager) -> None:
        config = config_manager.load()
        assert isinstance(config, AppConfig)
        assert config.active_theme == "midnight"
        assert config.session_autosave is True
        assert config.default_model_alias is None

    def test_save_creates_file(self, config_manager: ConfigManager) -> None:
        config_manager.save(AppConfig())
        assert config_manager.is_configured() is True

    def test_save_and_load_roundtrip(self, config_manager: ConfigManager) -> None:
        original = AppConfig(
            default_model_alias="google2",
            active_theme="aurora",
            web_search_enabled=True,
            context_warning_yellow=0.70,
            context_warning_orange=0.88,
            context_warning_red=0.97,
            session_autosave=False,
            search_provider="serpapi",
        )
        config_manager.save(original)
        loaded = config_manager.load()

        assert loaded.default_model_alias == "google2"
        assert loaded.active_theme == "aurora"
        assert loaded.web_search_enabled is True
        assert loaded.context_warning_yellow == pytest.approx(0.70)
        assert loaded.session_autosave is False
        assert loaded.search_provider == "serpapi"

    def test_load_raises_on_invalid_yaml(self, config_manager: ConfigManager) -> None:
        config_manager.paths.config_file.write_text("active_theme: !!bad_type")
        with pytest.raises(ConfigError):
            config_manager.load()

    def test_load_raises_on_invalid_values(self, config_manager: ConfigManager) -> None:
        config_manager.paths.config_file.write_text("active_theme: invalid_theme\n")
        with pytest.raises(ConfigError, match="invalid_theme"):
            config_manager.load()

    def test_load_empty_yaml_returns_defaults(self, config_manager: ConfigManager) -> None:
        config_manager.paths.config_file.write_text("")
        config = config_manager.load()
        assert config.active_theme == "midnight"

    def test_save_and_load_with_local_servers(self, config_manager: ConfigManager) -> None:
        config = AppConfig(local_servers={"ollama": "http://localhost:11434"})
        config_manager.save(config)
        loaded = config_manager.load()
        assert loaded.local_servers == {"ollama": "http://localhost:11434"}

    def test_save_and_load_with_plugin_settings(self, config_manager: ConfigManager) -> None:
        config = AppConfig(plugin_settings={"myplugin": {"key": "val"}})
        config_manager.save(config)
        loaded = config_manager.load()
        assert loaded.plugin_settings == {"myplugin": {"key": "val"}}

    def test_load_invalid_local_servers_falls_back_to_empty(
        self, config_manager: ConfigManager
    ) -> None:
        import yaml

        config_manager.paths.config_file.write_text(yaml.dump({"local_servers": "not-a-dict"}))
        loaded = config_manager.load()
        assert loaded.local_servers == {}

    def test_load_invalid_plugin_settings_falls_back_to_empty(
        self, config_manager: ConfigManager
    ) -> None:
        import yaml

        config_manager.paths.config_file.write_text(yaml.dump({"plugin_settings": "not-a-dict"}))
        loaded = config_manager.load()
        assert loaded.plugin_settings == {}

    def test_v2_defaults_preserve_v1_behavior(self, config_manager: ConfigManager) -> None:
        config = config_manager.load()
        assert config.ui_mode == "simple"
        assert config.active_rag_index is None
        assert config.embedding_backend == "local"
        assert config.browse_autonomy == "ask"
        assert config.browse_mode == "http"
        assert config.exec_mode == "ask"
        assert config.voice_model == "base"
        assert config.voice_language is None
        assert config.mouse_enabled is True
        assert config.notifications == {}

    def test_v2_fields_roundtrip(self, config_manager: ConfigManager) -> None:
        original = AppConfig(
            ui_mode="dashboard",
            active_rag_index="my-project",
            embedding_backend="api",
            browse_autonomy="auto",
            browse_mode="headless",
            exec_mode="auto",
            voice_model="turbo",
            voice_language="en",
            mouse_enabled=False,
            notifications={"rag_build": True, "slow_response": False},
        )
        config_manager.save(original)
        loaded = config_manager.load()

        assert loaded.ui_mode == "dashboard"
        assert loaded.active_rag_index == "my-project"
        assert loaded.embedding_backend == "api"
        assert loaded.browse_autonomy == "auto"
        assert loaded.browse_mode == "headless"
        assert loaded.exec_mode == "auto"
        assert loaded.voice_model == "turbo"
        assert loaded.voice_language == "en"
        assert loaded.mouse_enabled is False
        assert loaded.notifications == {"rag_build": True, "slow_response": False}

    def test_load_invalid_notifications_falls_back_to_empty(
        self, config_manager: ConfigManager
    ) -> None:
        import yaml

        config_manager.paths.config_file.write_text(yaml.dump({"notifications": "not-a-dict"}))
        loaded = config_manager.load()
        assert loaded.notifications == {}


class TestConfigManagerSaveOptionalFields:
    def test_save_with_spend_budget_soft_limit(self, config_manager: ConfigManager) -> None:
        config = AppConfig(spend_budget_soft_limit=10.0, spend_budget_period="monthly")
        config_manager.save(config)
        loaded = config_manager.load()
        assert loaded.spend_budget_soft_limit == pytest.approx(10.0)

    def test_save_with_mmos_fallback_order(self, config_manager: ConfigManager) -> None:
        config = AppConfig(mmos_fallback_order=("openai", "anthropic"))
        config_manager.save(config)
        loaded = config_manager.load()
        assert list(loaded.mmos_fallback_order) == ["openai", "anthropic"]

    def test_save_with_windows_allowed_paths(self, config_manager: ConfigManager) -> None:
        config = AppConfig(windows_allowed_paths=("C:\\Users",))
        config_manager.save(config)
        loaded = config_manager.load()
        assert list(loaded.windows_allowed_paths) == ["C:\\Users"]

    def test_save_with_windows_blocked_paths(self, config_manager: ConfigManager) -> None:
        config = AppConfig(windows_blocked_paths=("C:\\Windows\\System32",))
        config_manager.save(config)
        loaded = config_manager.load()
        assert list(loaded.windows_blocked_paths) == ["C:\\Windows\\System32"]

    def test_save_with_windows_audit_log_path(self, config_manager: ConfigManager) -> None:
        config = AppConfig(windows_audit_log_path="C:\\logs\\audit.log")
        config_manager.save(config)
        loaded = config_manager.load()
        assert loaded.windows_audit_log_path == "C:\\logs\\audit.log"

    def test_save_with_windows_blocked_apps_non_default(
        self, config_manager: ConfigManager
    ) -> None:
        custom_apps = ("custom.exe", "other.exe")
        config = AppConfig(windows_blocked_apps=custom_apps)
        config_manager.save(config)
        loaded = config_manager.load()
        assert list(loaded.windows_blocked_apps) == list(custom_apps)


class TestResolvePathsWithoutXdg:
    def test_default_paths_use_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        from anythink.config.manager import _resolve_paths

        paths = _resolve_paths()
        assert ".config" in str(paths.config_dir) or "anythink" in str(paths.config_dir)
        assert "anythink" in str(paths.config_dir)

    def test_paths_use_xdg_when_env_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        from anythink.config.manager import _resolve_paths

        paths = _resolve_paths()
        assert str(tmp_path / "cfg") in str(paths.config_dir)
