"""AppContext — dependency-injection container for the Anythink app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import IO

from rich.console import Console

from anythink.config.manager import ConfigManager, Paths, _resolve_paths
from anythink.config.models import ModelRegistry
from anythink.config.personas import PersonaManager
from anythink.config.schema import AppConfig
from anythink.config.templates import TemplateManager
from anythink.embeddings.registry import EmbeddingRegistry
from anythink.keys.manager import KeyManager
from anythink.mcp.builtin.filesystem import FilesystemServer
from anythink.mcp.builtin.rag import RAGServer
from anythink.mcp.builtin.search import SearchServer
from anythink.mcp.builtin.sessions import SessionsServer
from anythink.mcp.manager import MCPManager
from anythink.notify.notifier import Notifier
from anythink.plugins.manager import PluginManager
from anythink.providers.registry import ProviderRegistry
from anythink.rag.manager import RAGManager
from anythink.schedule.manager import ScheduleManager
from anythink.search.registry import SearchRegistry
from anythink.session.manager import SessionManager
from anythink.spend.tracker import SpendTracker
from anythink.tools.base import ApprovalMode
from anythink.tools.runner import ToolRunner
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
    session_manager: SessionManager
    search_registry: SearchRegistry
    plugin_manager: PluginManager
    rag_manager: RAGManager
    embedding_registry: EmbeddingRegistry
    tool_runner: ToolRunner
    mcp_manager: MCPManager
    notifier: Notifier
    spend_tracker: SpendTracker
    template_manager: TemplateManager
    schedule_manager: ScheduleManager

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
        key_manager = KeyManager(paths=resolved)

        embedding_registry = EmbeddingRegistry.from_entry_points()
        rag_manager = RAGManager(rag_dir=resolved.rag_dir, cache_dir=resolved.rag_cache_dir)

        # Activate the persisted index from config if one is set
        if config.active_rag_index:
            rag_manager.use_index(config.active_rag_index)

        tool_runner = ToolRunner(ApprovalMode(config.exec_mode))
        notifier = Notifier(config_toggles=dict(config.notifications))

        session_manager = SessionManager(sessions_dir=resolved.sessions_dir)
        search_reg = SearchRegistry.from_entry_points(
            api_keys={"serpapi": key_manager.get_key("serpapi")}
        )
        emb = EmbeddingRegistry.from_entry_points().get_available(config.embedding_backend)
        mcp_manager = MCPManager(
            builtin_servers=[
                FilesystemServer(),
                SessionsServer(session_manager),
                RAGServer(rag_manager, emb),
                SearchServer(search_reg, preferred=config.search_provider),
            ]
        )

        spend_tracker = SpendTracker(log_file=resolved.spend_log_file)
        spend_tracker.prune(keep_days=90)

        return cls(
            config=config,
            paths=resolved,
            console=console,
            theme=theme,
            config_manager=config_manager,
            key_manager=key_manager,
            provider_registry=ProviderRegistry(),
            model_registry=ModelRegistry(path=resolved.models_file),
            persona_manager=PersonaManager(path=resolved.personas_file),
            session_manager=session_manager,
            search_registry=search_reg,
            plugin_manager=PluginManager(),
            rag_manager=rag_manager,
            embedding_registry=embedding_registry,
            tool_runner=tool_runner,
            mcp_manager=mcp_manager,
            notifier=notifier,
            spend_tracker=spend_tracker,
            template_manager=TemplateManager(path=resolved.templates_file),
            schedule_manager=ScheduleManager(path=resolved.schedules_file),
        )
