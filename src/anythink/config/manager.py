"""XDG-compliant config manager for Anythink."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from anythink.config.schema import AppConfig
from anythink.exceptions import ConfigError


@dataclass(frozen=True)
class Paths:
    """Resolved XDG Base Directory paths for Anythink."""

    config_dir: Path
    data_dir: Path
    state_dir: Path
    cache_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.yaml"

    @property
    def models_file(self) -> Path:
        return self.config_dir / "models.yaml"

    @property
    def personas_file(self) -> Path:
        return self.config_dir / "personas.yaml"

    @property
    def plugins_file(self) -> Path:
        return self.config_dir / "plugins.yaml"

    @property
    def keyring_index_file(self) -> Path:
        return self.config_dir / "keyring_index.yaml"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def logs_dir(self) -> Path:
        return self.state_dir / "logs"

    def ensure_dirs(self) -> None:
        for d in (self.config_dir, self.data_dir, self.state_dir, self.cache_dir, self.sessions_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


def _resolve_paths() -> Paths:
    def _xdg(env_var: str, default_rel: str) -> Path:
        val = os.environ.get(env_var)
        if val:
            return Path(val) / "anythink"
        return Path.home() / default_rel / "anythink"

    return Paths(
        config_dir=_xdg("XDG_CONFIG_HOME", ".config"),
        data_dir=_xdg("XDG_DATA_HOME", ".local/share"),
        state_dir=_xdg("XDG_STATE_HOME", ".local/state"),
        cache_dir=_xdg("XDG_CACHE_HOME", ".cache"),
    )


_VALID_THEMES = frozenset({"midnight", "aurora", "ember", "arctic"})


def validate_config(raw: dict[str, Any]) -> list[ConfigError]:
    """Validate raw config dict and return a list of errors (never raises)."""
    errors: list[ConfigError] = []

    theme = raw.get("active_theme", "midnight")
    if theme not in _VALID_THEMES:
        errors.append(ConfigError(f"Invalid theme '{theme}'. Valid themes: {sorted(_VALID_THEMES)}"))

    for field in ("context_warning_yellow", "context_warning_orange", "context_warning_red"):
        val = raw.get(field)
        if val is not None and not isinstance(val, (int, float)):
            errors.append(ConfigError(f"'{field}' must be a number, got {type(val).__name__}"))
        elif val is not None and not (0.0 <= float(val) <= 1.0):
            errors.append(ConfigError(f"'{field}' must be between 0.0 and 1.0, got {val}"))

    return errors


class ConfigManager:
    """Loads and saves the Anythink configuration."""

    def __init__(self, paths: Paths | None = None) -> None:
        self.paths = paths or _resolve_paths()

    def is_configured(self) -> bool:
        return self.paths.config_file.exists()

    def load(self) -> AppConfig:
        if not self.paths.config_file.exists():
            return AppConfig()

        try:
            raw: dict[str, Any] = yaml.safe_load(self.paths.config_file.read_text()) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"Failed to parse config.yaml: {e}") from e

        errors = validate_config(raw)
        if errors:
            messages = "\n".join(f"  - {e}" for e in errors)
            raise ConfigError(f"Configuration errors found:\n{messages}")

        local_servers = raw.get("local_servers", {})
        plugin_settings = raw.get("plugin_settings", {})
        if not isinstance(local_servers, dict):
            local_servers = {}
        if not isinstance(plugin_settings, dict):
            plugin_settings = {}

        return AppConfig(
            default_model_alias=raw.get("default_model_alias"),
            active_theme=raw.get("active_theme", "midnight"),
            web_search_enabled=bool(raw.get("web_search_enabled", False)),
            context_warning_yellow=float(raw.get("context_warning_yellow", 0.60)),
            context_warning_orange=float(raw.get("context_warning_orange", 0.85)),
            context_warning_red=float(raw.get("context_warning_red", 0.95)),
            session_autosave=bool(raw.get("session_autosave", True)),
            search_provider=str(raw.get("search_provider", "duckduckgo")),
            local_servers=local_servers,
            plugin_settings=plugin_settings,
        )

    def save(self, config: AppConfig) -> None:
        self.paths.ensure_dirs()
        data: dict[str, Any] = {
            "active_theme": config.active_theme,
            "web_search_enabled": config.web_search_enabled,
            "context_warning_yellow": config.context_warning_yellow,
            "context_warning_orange": config.context_warning_orange,
            "context_warning_red": config.context_warning_red,
            "session_autosave": config.session_autosave,
            "search_provider": config.search_provider,
        }
        if config.default_model_alias:
            data["default_model_alias"] = config.default_model_alias
        if config.local_servers:
            data["local_servers"] = config.local_servers
        if config.plugin_settings:
            data["plugin_settings"] = config.plugin_settings

        self.paths.config_file.write_text(yaml.dump(data, default_flow_style=False, sort_keys=True))
