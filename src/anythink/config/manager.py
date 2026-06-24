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

    @property
    def rag_dir(self) -> Path:
        """YAML metadata for named RAG indexes."""
        return self.data_dir / "rag"

    @property
    def rag_cache_dir(self) -> Path:
        """Persisted vector stores (binary blobs)."""
        return self.cache_dir / "rag"

    # --- V3 paths ---

    @property
    def templates_file(self) -> Path:
        return self.config_dir / "templates.yaml"

    @property
    def schedules_file(self) -> Path:
        return self.config_dir / "schedules.yaml"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def spend_log_file(self) -> Path:
        return self.data_dir / "spend.yaml"

    @property
    def api_debug_log_file(self) -> Path:
        return self.state_dir / "logs" / "api_debug.log"

    @property
    def debug_exports_dir(self) -> Path:
        return self.data_dir / "debug_exports"

    # --- V4 MMOS paths ---

    @property
    def model_capability_registry_file(self) -> Path:
        return self.data_dir / "model_registry.json"

    @property
    def model_capability_registry_user_file(self) -> Path:
        return self.config_dir / "model_registry_user.json"

    @property
    def optimize_settings_file(self) -> Path:
        return self.config_dir / "optimize_settings.yaml"

    @property
    def routing_rules_file(self) -> Path:
        return self.config_dir / "routing_rules.yaml"

    @property
    def rate_limit_state_file(self) -> Path:
        return self.state_dir / "rate_limit_state.json"

    @property
    def plans_dir(self) -> Path:
        return self.data_dir / "plans"

    def ensure_dirs(self) -> None:
        for d in (
            self.config_dir,
            self.data_dir,
            self.state_dir,
            self.cache_dir,
            self.sessions_dir,
            self.logs_dir,
            self.rag_dir,
            self.rag_cache_dir,
            self.exports_dir,
            self.plans_dir,
        ):
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


_VALID_THEMES = frozenset(
    {
        "midnight",
        "aurora",
        "ember",
        "arctic",
        "charcoal",
        "linen",
        "rose",
        "dracula",
    }
)

# V2 enumerated config fields: field name -> allowed values.
_ENUM_FIELDS: dict[str, frozenset[str]] = {
    "ui_mode": frozenset({"simple", "dashboard"}),
    "embedding_backend": frozenset({"local", "api"}),
    "browse_autonomy": frozenset({"ask", "auto"}),
    "browse_mode": frozenset({"http", "headless"}),
    "exec_mode": frozenset({"ask", "auto"}),
    "voice_model": frozenset({"tiny", "base", "small", "medium", "large", "turbo"}),
    # V2.2
    "bubble_style": frozenset({"boxed", "minimal"}),
    "density": frozenset({"comfortable", "compact"}),
    "timestamps": frozenset({"relative", "absolute"}),
    "icon_style": frozenset({"unicode", "ascii"}),
    # V3
    "spend_budget_period": frozenset({"daily", "monthly"}),
    # RAG V2
    "rag_retrieval_strategy": frozenset({"vector", "bm25", "hybrid", "mmr"}),
    "rag_chunk_strategy": frozenset({"fixed", "sentence", "paragraph", "semantic", "code", "heading"}),
    "rag_no_match_behavior": frozenset({"graceful", "passthrough"}),
    # V4 MMOS
    "mmos_mode": frozenset({"online", "offline", "auto"}),
    "mmos_priority": frozenset({"quality", "reliability", "hybrid"}),
    "mmos_history_mode": frozenset({"semantic", "recency", "model_decides"}),
    "mmos_mixing_mode": frozenset({"routing", "ensemble", "chaining", "decompose"}),
    "mmos_orchestration": frozenset({"deterministic", "meta_llm", "auto"}),
}


def validate_config(raw: dict[str, Any]) -> list[ConfigError]:
    """Validate raw config dict and return a list of errors (never raises)."""
    errors: list[ConfigError] = []

    theme = raw.get("active_theme", "midnight")
    if theme not in _VALID_THEMES:
        errors.append(
            ConfigError(f"Invalid theme '{theme}'. Valid themes: {sorted(_VALID_THEMES)}")
        )

    for field in ("context_warning_yellow", "context_warning_orange", "context_warning_red"):
        val = raw.get(field)
        if val is not None and not isinstance(val, (int, float)):
            errors.append(ConfigError(f"'{field}' must be a number, got {type(val).__name__}"))
        elif val is not None and not (0.0 <= float(val) <= 1.0):
            errors.append(ConfigError(f"'{field}' must be between 0.0 and 1.0, got {val}"))

    for name, allowed in _ENUM_FIELDS.items():
        val = raw.get(name)
        if val is not None and val not in allowed:
            errors.append(
                ConfigError(f"Invalid '{name}' value '{val}'. Allowed: {sorted(allowed)}")
            )

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
        notifications = raw.get("notifications", {})
        if not isinstance(local_servers, dict):
            local_servers = {}
        if not isinstance(plugin_settings, dict):
            plugin_settings = {}
        if not isinstance(notifications, dict):
            notifications = {}

        spend_budget_soft_limit = raw.get("spend_budget_soft_limit")
        mmos_fallback_raw = raw.get("mmos_fallback_order", [])
        mmos_fallback: tuple[str, ...] = (
            tuple(str(x) for x in mmos_fallback_raw) if isinstance(mmos_fallback_raw, list) else ()
        )
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
            ui_mode=str(raw.get("ui_mode", "simple")),
            active_rag_index=raw.get("active_rag_index"),
            embedding_backend=str(raw.get("embedding_backend", "local")),
            browse_autonomy=str(raw.get("browse_autonomy", "ask")),
            browse_mode=str(raw.get("browse_mode", "http")),
            exec_mode=str(raw.get("exec_mode", "ask")),
            voice_model=str(raw.get("voice_model", "base")),
            voice_language=raw.get("voice_language"),
            mouse_enabled=bool(raw.get("mouse_enabled", True)),
            notifications=notifications,
            spend_tracking=bool(raw.get("spend_tracking", True)),
            spend_budget_soft_limit=(
                float(spend_budget_soft_limit) if spend_budget_soft_limit is not None else None
            ),
            spend_budget_period=str(raw.get("spend_budget_period", "monthly")),
            # RAG V2
            rag_threshold=float(raw.get("rag_threshold", 0.65)),
            rag_top_k=int(raw.get("rag_top_k", 3)),
            rag_reranking=bool(raw.get("rag_reranking", False)),
            rag_retrieval_strategy=str(raw.get("rag_retrieval_strategy", "vector")),
            rag_chunk_strategy=str(raw.get("rag_chunk_strategy", "fixed")),
            rag_chunk_size=int(raw.get("rag_chunk_size", 512)),
            rag_chunk_overlap=int(raw.get("rag_chunk_overlap", 100)),
            rag_quality_indicators=bool(raw.get("rag_quality_indicators", True)),
            rag_confidence_display=bool(raw.get("rag_confidence_display", True)),
            rag_no_match_behavior=str(raw.get("rag_no_match_behavior", "graceful")),
            # V4 MMOS
            mmos_enabled=bool(raw.get("mmos_enabled", False)),
            mmos_mode=str(raw.get("mmos_mode", "auto")),
            mmos_priority=str(raw.get("mmos_priority", "quality")),
            mmos_microprompt=bool(raw.get("mmos_microprompt", True)),
            mmos_history_mode=str(raw.get("mmos_history_mode", "semantic")),
            mmos_history_max_tokens=int(raw.get("mmos_history_max_tokens", 2048)),
            mmos_mixing_mode=str(raw.get("mmos_mixing_mode", "routing")),
            mmos_plan_mode=bool(raw.get("mmos_plan_mode", True)),
            mmos_orchestration=str(raw.get("mmos_orchestration", "auto")),
            mmos_fallback_order=mmos_fallback,
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
            "ui_mode": config.ui_mode,
            "embedding_backend": config.embedding_backend,
            "browse_autonomy": config.browse_autonomy,
            "browse_mode": config.browse_mode,
            "exec_mode": config.exec_mode,
            "voice_model": config.voice_model,
            "mouse_enabled": config.mouse_enabled,
        }
        if config.default_model_alias:
            data["default_model_alias"] = config.default_model_alias
        if config.local_servers:
            data["local_servers"] = config.local_servers
        if config.plugin_settings:
            data["plugin_settings"] = config.plugin_settings
        if config.active_rag_index:
            data["active_rag_index"] = config.active_rag_index
        if config.voice_language:
            data["voice_language"] = config.voice_language
        # Always persist notifications dict — empty dict means "all defaults"
        data["notifications"] = dict(config.notifications)

        # V3 spend fields
        data["spend_tracking"] = config.spend_tracking
        data["spend_budget_period"] = config.spend_budget_period
        if config.spend_budget_soft_limit is not None:
            data["spend_budget_soft_limit"] = config.spend_budget_soft_limit

        # RAG V2 fields
        data["rag_threshold"] = config.rag_threshold
        data["rag_top_k"] = config.rag_top_k
        data["rag_reranking"] = config.rag_reranking
        data["rag_retrieval_strategy"] = config.rag_retrieval_strategy
        data["rag_chunk_strategy"] = config.rag_chunk_strategy
        data["rag_chunk_size"] = config.rag_chunk_size
        data["rag_chunk_overlap"] = config.rag_chunk_overlap
        data["rag_quality_indicators"] = config.rag_quality_indicators
        data["rag_confidence_display"] = config.rag_confidence_display
        data["rag_no_match_behavior"] = config.rag_no_match_behavior

        # V4 MMOS fields
        data["mmos_enabled"] = config.mmos_enabled
        data["mmos_mode"] = config.mmos_mode
        data["mmos_priority"] = config.mmos_priority
        data["mmos_microprompt"] = config.mmos_microprompt
        data["mmos_history_mode"] = config.mmos_history_mode
        data["mmos_history_max_tokens"] = config.mmos_history_max_tokens
        data["mmos_mixing_mode"] = config.mmos_mixing_mode
        data["mmos_plan_mode"] = config.mmos_plan_mode
        data["mmos_orchestration"] = config.mmos_orchestration
        if config.mmos_fallback_order:
            data["mmos_fallback_order"] = list(config.mmos_fallback_order)

        self.paths.config_file.write_text(yaml.dump(data, default_flow_style=False, sort_keys=True))
