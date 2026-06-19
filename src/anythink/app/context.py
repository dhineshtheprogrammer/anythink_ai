"""AppContext — dependency-injection container for the Anythink app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import IO

from rich.console import Console

from anythink.config.manager import ConfigManager, Paths, _resolve_paths
from anythink.config.models import ModelRegistry
from anythink.config.personas import PersonaManager
from anythink.config.schema import AppConfig
from anythink.keys.manager import KeyManager
from anythink.providers.registry import ProviderRegistry
from anythink.ui.console import make_console
from anythink.ui.theme import Theme, get_theme


@dataclass
class AppContext:
    """Mutable container for every Anythink sub-system.

    Constructed once at startup and threaded through the call stack.
    No module-level globals; tests inject Console(file=StringIO()) here.
    """

    config: AppConfig
    paths: Paths
    console: Console
    theme: Theme
    config_manager: ConfigManager
    key_manager: KeyManager
    provider_registry: ProviderRegistry
    model_registry: ModelRegistry
    persona_manager: PersonaManager

    @classmethod
    def create(
        cls,
        paths: Paths | None = None,
        console_file: IO[str] | None = None,
    ) -> AppContext:
        """Build a fully wired AppContext from scratch."""
        resolved = paths or _resolve_paths()
        resolved.ensure_dirs()

        config_manager = ConfigManager(paths=resolved)
        config = config_manager.load()
        theme = get_theme(config.active_theme)
        console = make_console(theme, file=console_file)

        return cls(
            config=config,
            paths=resolved,
            console=console,
            theme=theme,
            config_manager=config_manager,
            key_manager=KeyManager(paths=resolved),
            provider_registry=ProviderRegistry(),
            model_registry=ModelRegistry(path=resolved.models_file),
            persona_manager=PersonaManager(path=resolved.personas_file),
        )
