"""AppConfig dataclass and defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AppConfig:
    """Immutable application configuration resolved at startup."""

    default_model_alias: str | None = None
    active_theme: str = "midnight"
    web_search_enabled: bool = False
    context_warning_yellow: float = 0.60
    context_warning_orange: float = 0.85
    context_warning_red: float = 0.95
    session_autosave: bool = True
    search_provider: str = "duckduckgo"
    local_servers: dict[str, str] = field(default_factory=dict)
    plugin_settings: dict[str, Any] = field(default_factory=dict)

    # --- V2 fields (safe defaults preserve V1 behavior) ---
    ui_mode: str = "simple"  # "simple" | "dashboard"
    active_rag_index: str | None = None
    embedding_backend: str = "local"  # "local" | "api"
    browse_autonomy: str = "ask"  # "ask" | "auto"
    browse_mode: str = "http"  # "http" | "headless"
    exec_mode: str = "ask"  # "ask" | "auto"
    voice_model: str = "base"  # tiny|base|small|medium|large|turbo
    voice_language: str | None = None  # None = auto-detect
    mouse_enabled: bool = True
    notifications: dict[str, bool] = field(default_factory=dict)  # per-type toggles

    # --- V2.2 fields ---
    bubble_style: str = "boxed"  # "boxed" | "minimal"
    density: str = "comfortable"  # "comfortable" | "compact"
    show_avatars: bool = False
    timestamps: str = "relative"  # "relative" | "absolute"
    icon_style: str = "unicode"  # "unicode" | "ascii"

    # --- V3 fields ---
    spend_tracking: bool = True
    spend_budget_soft_limit: float | None = None  # USD; None = no limit
    spend_budget_period: str = "monthly"  # "daily" | "monthly"

    # --- V3.2 debug fields ---
    debug_mode: bool = False
    debug_level: int = 2  # 1 | 2 | 3
    debug_api_logging: bool = False

    VALID_THEMES: frozenset[str] = field(
        default=frozenset(
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
        ),
        init=False,
        repr=False,
        compare=False,
    )
