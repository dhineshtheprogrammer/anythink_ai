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

    # --- RAG V2 fields ---
    rag_threshold: float = 0.65  # minimum relevance score for chunk injection
    rag_top_k: int = 3  # chunks retrieved per query (default)
    rag_reranking: bool = False  # cross-encoder re-ranking on/off
    rag_retrieval_strategy: str = "vector"  # "vector"|"bm25"|"hybrid"|"mmr"
    rag_chunk_strategy: str = "fixed"  # session-level override; per-index stored in IndexInfo
    rag_chunk_size: int = 512  # tokens per chunk (session-level default)
    rag_chunk_overlap: int = 100  # overlap tokens (session-level default)
    rag_quality_indicators: bool = True  # show confidence scores in response footer
    rag_confidence_display: bool = True  # show per-chunk relevance in expanded view
    rag_no_match_behavior: str = "graceful"  # "graceful" (3-option menu) | "passthrough" (ignore RAG)

    # --- V4 MMOS fields (mmos_enabled=False preserves pure V3 behaviour) ---
    mmos_enabled: bool = False
    mmos_mode: str = "auto"  # "online" | "offline" | "auto"
    mmos_priority: str = "quality"  # "quality" | "reliability" | "hybrid"
    mmos_microprompt: bool = True
    mmos_history_mode: str = "semantic"  # "semantic" | "recency" | "model_decides"
    mmos_history_max_tokens: int = 2048
    mmos_mixing_mode: str = "routing"  # "routing" | "ensemble" | "chaining" | "decompose"
    mmos_plan_mode: bool = True
    mmos_orchestration: str = "auto"  # "deterministic" | "meta_llm" | "auto"
    mmos_fallback_order: tuple[str, ...] = field(default_factory=tuple)

    # --- Windows MCP fields (windows_enabled=False is a no-op on all platforms) ---
    windows_enabled: bool = False
    windows_gui_mode: bool = False
    # Empty tuples → WindowsPathGuard populates OS-appropriate defaults at init
    windows_allowed_paths: tuple[str, ...] = field(default_factory=tuple)
    windows_blocked_paths: tuple[str, ...] = field(default_factory=tuple)
    windows_blocked_apps: tuple[str, ...] = (
        "regedit.exe",
        "cmd.exe",
        "powershell.exe",
        "mmc.exe",
    )
    windows_audit_log_enabled: bool = True
    windows_audit_log_path: str = ""  # empty → use XDG state dir default
    windows_screenshot_max_px: int = 1920
    windows_notification_app_name: str = "Anythink"
    windows_apps_cache_ttl_minutes: int = 60

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
