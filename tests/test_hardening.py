"""Phase-9 hardening tests: config validation, perf guards, version, extras."""

from __future__ import annotations

from io import StringIO

import pytest

from anythink import __version__
from anythink.config.manager import ConfigManager, Paths, validate_config
from anythink.config.schema import AppConfig
from anythink.exceptions import ConfigError

# ── Version ───────────────────────────────────────────────────────────────────


class TestVersion:
    def test_version_is_3_1_0(self) -> None:
        assert __version__ == "3.1.0"

    def test_version_is_string(self) -> None:
        assert isinstance(__version__, str)

    def test_version_has_three_parts(self) -> None:
        parts = __version__.split(".")
        assert len(parts) == 3
        for p in parts:
            assert p.isdigit()


# ── Config validation — V2 enum fields ────────────────────────────────────────


class TestValidateConfigV2Fields:
    def test_valid_ui_mode_simple(self) -> None:
        assert validate_config({"ui_mode": "simple"}) == []

    def test_valid_ui_mode_dashboard(self) -> None:
        assert validate_config({"ui_mode": "dashboard"}) == []

    def test_invalid_ui_mode(self) -> None:
        errors = validate_config({"ui_mode": "panel"})
        assert len(errors) == 1
        assert "ui_mode" in str(errors[0])

    def test_valid_exec_modes(self) -> None:
        assert validate_config({"exec_mode": "ask"}) == []
        assert validate_config({"exec_mode": "auto"}) == []

    def test_invalid_exec_mode(self) -> None:
        errors = validate_config({"exec_mode": "always"})
        assert errors

    def test_valid_browse_autonomy(self) -> None:
        assert validate_config({"browse_autonomy": "ask"}) == []
        assert validate_config({"browse_autonomy": "auto"}) == []

    def test_valid_browse_mode(self) -> None:
        assert validate_config({"browse_mode": "http"}) == []
        assert validate_config({"browse_mode": "headless"}) == []

    def test_invalid_browse_mode(self) -> None:
        errors = validate_config({"browse_mode": "proxy"})
        assert errors

    def test_all_valid_voice_models(self) -> None:
        for model in ("tiny", "base", "small", "medium", "large", "turbo"):
            assert validate_config({"voice_model": model}) == []

    def test_invalid_voice_model(self) -> None:
        errors = validate_config({"voice_model": "giga"})
        assert errors

    def test_valid_embedding_backends(self) -> None:
        assert validate_config({"embedding_backend": "local"}) == []
        assert validate_config({"embedding_backend": "api"}) == []

    def test_invalid_embedding_backend(self) -> None:
        errors = validate_config({"embedding_backend": "chroma"})
        assert errors

    def test_multiple_errors_accumulated(self) -> None:
        errors = validate_config({"ui_mode": "bad", "exec_mode": "bad", "browse_mode": "bad"})
        assert len(errors) == 3

    def test_empty_config_valid(self) -> None:
        assert validate_config({}) == []

    def test_valid_theme_passes(self) -> None:
        for theme in ("midnight", "aurora", "ember", "arctic"):
            assert validate_config({"active_theme": theme}) == []

    def test_invalid_theme_fails(self) -> None:
        errors = validate_config({"active_theme": "neon"})
        assert errors


# ── Config save / load round-trip (V2 fields) ─────────────────────────────────


class TestConfigRoundTrip:
    def test_notifications_persisted(self, xdg_dirs: Paths) -> None:
        mgr = ConfigManager(paths=xdg_dirs)
        cfg = AppConfig(notifications={"rag_build_done": False, "slow_response": True})
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.notifications.get("rag_build_done") is False
        assert loaded.notifications.get("slow_response") is True

    def test_empty_notifications_persisted(self, xdg_dirs: Paths) -> None:
        mgr = ConfigManager(paths=xdg_dirs)
        cfg = AppConfig(notifications={})
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.notifications == {}

    def test_voice_model_round_trip(self, xdg_dirs: Paths) -> None:
        mgr = ConfigManager(paths=xdg_dirs)
        cfg = AppConfig(voice_model="small")
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.voice_model == "small"

    def test_voice_language_round_trip(self, xdg_dirs: Paths) -> None:
        mgr = ConfigManager(paths=xdg_dirs)
        cfg = AppConfig(voice_language="en")
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.voice_language == "en"

    def test_voice_language_none_round_trip(self, xdg_dirs: Paths) -> None:
        mgr = ConfigManager(paths=xdg_dirs)
        cfg = AppConfig(voice_language=None)
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.voice_language is None

    def test_exec_mode_round_trip(self, xdg_dirs: Paths) -> None:
        mgr = ConfigManager(paths=xdg_dirs)
        cfg = AppConfig(exec_mode="auto")
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.exec_mode == "auto"

    def test_browse_mode_round_trip(self, xdg_dirs: Paths) -> None:
        mgr = ConfigManager(paths=xdg_dirs)
        cfg = AppConfig(browse_mode="headless", browse_autonomy="auto")
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.browse_mode == "headless"
        assert loaded.browse_autonomy == "auto"

    def test_active_rag_index_round_trip(self, xdg_dirs: Paths) -> None:
        mgr = ConfigManager(paths=xdg_dirs)
        cfg = AppConfig(active_rag_index="my-code")
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.active_rag_index == "my-code"

    def test_invalid_config_raises_on_load(self, xdg_dirs: Paths) -> None:
        bad_yaml = "active_theme: neon\n"
        xdg_dirs.config_file.write_text(bad_yaml)
        mgr = ConfigManager(paths=xdg_dirs)
        with pytest.raises(ConfigError, match="theme"):
            mgr.load()


# ── AppConfig defaults — all V2 fields ────────────────────────────────────────


class TestAppConfigDefaults:
    def test_ui_mode_default(self) -> None:
        assert AppConfig().ui_mode == "simple"

    def test_exec_mode_default(self) -> None:
        assert AppConfig().exec_mode == "ask"

    def test_browse_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.browse_autonomy == "ask"
        assert cfg.browse_mode == "http"

    def test_voice_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.voice_model == "base"
        assert cfg.voice_language is None

    def test_notifications_default_empty(self) -> None:
        assert AppConfig().notifications == {}

    def test_mouse_enabled_default(self) -> None:
        assert AppConfig().mouse_enabled is True

    def test_embedding_backend_default(self) -> None:
        assert AppConfig().embedding_backend == "local"

    def test_valid_themes_set(self) -> None:
        cfg = AppConfig()
        assert "midnight" in cfg.VALID_THEMES
        assert "aurora" in cfg.VALID_THEMES
        assert "ember" in cfg.VALID_THEMES
        assert "arctic" in cfg.VALID_THEMES


# ── Notifier integration via AppContext ───────────────────────────────────────


class TestNotifierInContext:
    def test_notifier_created_in_context(self, xdg_dirs: Paths) -> None:
        from anythink.app.context import AppContext

        ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
        assert ctx.notifier is not None
        assert ctx.notifier.enabled  # default: on

    def test_notifier_respects_config_toggles(self, xdg_dirs: Paths) -> None:
        from anythink.app.context import AppContext

        mgr = ConfigManager(paths=xdg_dirs)
        mgr.save(AppConfig(notifications={"rag_build_done": False}))
        ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
        assert not ctx.notifier.is_type_enabled("rag_build_done")
        assert ctx.notifier.is_type_enabled("slow_response")  # others still on
