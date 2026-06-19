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

    VALID_THEMES: frozenset[str] = field(
        default=frozenset({"midnight", "aurora", "ember", "arctic"}), init=False, repr=False, compare=False
    )
