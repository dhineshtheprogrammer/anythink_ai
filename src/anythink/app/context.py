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
from anythink.debug.manager import DebugManager
from anythink.embeddings.registry import EmbeddingRegistry
from anythink.keys.manager import KeyManager
from anythink.mcp.builtin.filesystem import FilesystemServer
from anythink.mcp.builtin.rag import RAGServer
from anythink.mcp.builtin.search import SearchServer
from anythink.mcp.builtin.sessions import SessionsServer
from anythink.mcp.manager import MCPManager
from anythink.notify.notifier import Notifier
from anythink.optimize.classifier import IntentClassifier
from anythink.optimize.context_engine import ContextRelevanceEngine
from anythink.optimize.mixing import MixingOrchestrator
from anythink.optimize.plan_engine import PlanEngine
from anythink.optimize.plan_runner import PlanRunner
from anythink.optimize.rate_limit import RateLimitManager
from anythink.optimize.registry import ModelCapabilityRegistry
from anythink.optimize.router import RoutingEngine
from anythink.optimize.rules import RoutingRulesLoader
from anythink.optimize.settings_manager import OptimizeSettingsManager
from anythink.plugins.manager import PluginManager
from anythink.providers.registry import ProviderRegistry
from anythink.rag.manager import RAGManager
from anythink.schedule.manager import ScheduleManager
from anythink.search.cache import SearchCache
from anythink.search.orchestrator import SearchOrchestrator
from anythink.search.registry import SearchRegistry
from anythink.session.manager import SessionManager
from anythink.spend.tracker import SpendTracker
from anythink.tools.base import ApprovalMode
from anythink.tools.runner import ToolRunner
from anythink.ui.console import make_console
from anythink.ui.theme import Theme, get_theme

# Known vision-capable model ID fragments — used to decide whether to pass
# vision_capable=True to WindowsScreenshotServer.
_VISION_MODEL_HINTS = frozenset(
    {"claude-3", "claude-4", "claude-sonnet", "claude-opus", "claude-haiku",
     "gpt-4o", "gemini", "gpt-4-vision", "llava"}
)


def _check_vision_capable(config: AppConfig) -> bool:
    alias = config.default_model_alias
    if not alias:
        return False
    alias_lower = alias.lower()
    return any(hint in alias_lower for hint in _VISION_MODEL_HINTS)


def _build_windows_servers(config: AppConfig, paths: "Paths") -> list:  # type: ignore[type-arg]
    """Return the 10 Windows MCP servers when running on Windows with windows_enabled=True.

    All imports are deferred so non-Windows platforms never load Windows-only code.
    Returns an empty list on non-Windows or when the feature is disabled.
    """
    import sys as _sys
    if _sys.platform != "win32" or not config.windows_enabled:
        return []

    from anythink.mcp.builtin.windows_apps import WindowsAppsServer
    from anythink.mcp.builtin.windows_clipboard import WindowsClipboardServer
    from anythink.mcp.builtin.windows_explorer import WindowsExplorerServer
    from anythink.mcp.builtin.windows_filesystem import WindowsFilesystemServer
    from anythink.mcp.builtin.windows_notification import WindowsNotificationServer
    from anythink.mcp.builtin.windows_process import WindowsProcessServer
    from anythink.mcp.builtin.windows_screenshot import WindowsScreenshotServer
    from anythink.mcp.builtin.windows_settings import WindowsSettingsServer
    from anythink.mcp.builtin.windows_system import WindowsSystemServer
    from anythink.mcp.builtin.windows_window import WindowsWindowServer
    from anythink.mcp.windows.audit import WindowsAuditLog
    from anythink.mcp.windows.paths import WindowsPathGuard
    from anythink.mcp.windows.safety import WindowsSafetyChecker

    audit_path = config.windows_audit_log_path or str(
        paths.state_dir / "logs" / "windows_audit.log"
    )
    path_guard = WindowsPathGuard(config)
    safety = WindowsSafetyChecker()
    audit = WindowsAuditLog(audit_path)
    vision_capable = _check_vision_capable(config)

    return [
        WindowsFilesystemServer(path_guard, safety, audit),
        WindowsExplorerServer(path_guard, safety, audit),
        WindowsAppsServer(
            safety,
            audit,
            blocked_apps=config.windows_blocked_apps,
            cache_ttl_minutes=config.windows_apps_cache_ttl_minutes,
        ),
        WindowsWindowServer(safety, audit, gui_mode=config.windows_gui_mode),
        WindowsProcessServer(safety, audit, blocked_apps=config.windows_blocked_apps),
        WindowsSystemServer(audit),
        WindowsSettingsServer(safety, audit),
        WindowsClipboardServer(safety, audit),
        WindowsScreenshotServer(
            safety,
            audit,
            vision_capable=vision_capable,
            gui_mode=config.windows_gui_mode,
            max_px=config.windows_screenshot_max_px,
            path_guard=path_guard,
        ),
        WindowsNotificationServer(
            safety,
            audit,
            app_name=config.windows_notification_app_name,
        ),
    ]


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
    search_cache: SearchCache
    search_orchestrator: SearchOrchestrator
    plugin_manager: PluginManager
    rag_manager: RAGManager
    embedding_registry: EmbeddingRegistry
    tool_runner: ToolRunner
    mcp_manager: MCPManager
    notifier: Notifier
    spend_tracker: SpendTracker
    template_manager: TemplateManager
    schedule_manager: ScheduleManager
    debug_manager: DebugManager
    # --- V4 MMOS ---
    mmos_registry: ModelCapabilityRegistry
    mmos_settings: OptimizeSettingsManager
    rate_limit_manager: RateLimitManager
    routing_engine: RoutingEngine
    context_engine: ContextRelevanceEngine
    plan_engine: PlanEngine
    plan_runner: PlanRunner
    mixing_orchestrator: MixingOrchestrator

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
            api_keys={
                "serpapi": key_manager.get_key("serpapi"),
                "exa": key_manager.get_key("exa"),
                "newsapi": key_manager.get_key("newsapi"),
                "bing": key_manager.get_key("bing"),
                "google_cse": key_manager.get_key("google_cse"),
            }
        )
        search_cache = SearchCache(ttl_minutes=config.search_cache_ttl_minutes)
        search_orchestrator = SearchOrchestrator(
            search_reg,
            search_cache,
            preferred_backend=config.search_provider,
            max_searches=config.search_max_per_response,
        )
        emb = EmbeddingRegistry.from_entry_points().get_available(config.embedding_backend)
        mcp_manager = MCPManager(
            builtin_servers=[
                FilesystemServer(),
                SessionsServer(session_manager),
                RAGServer(rag_manager, emb),
                SearchServer(search_reg, preferred=config.search_provider),
                *_build_windows_servers(config, resolved),
            ]
        )

        spend_tracker = SpendTracker(log_file=resolved.spend_log_file)
        spend_tracker.prune(keep_days=90)

        debug_manager = DebugManager()
        if config.debug_mode:
            debug_manager.enable(level=config.debug_level)
        if config.debug_api_logging:
            debug_manager.toggle_api_logging()

        # V4 MMOS subsystems
        mmos_registry = ModelCapabilityRegistry(
            bundled_path=None,  # loads from importlib.resources (anythink.data)
            user_path=resolved.model_capability_registry_user_file,
        )
        mmos_settings = OptimizeSettingsManager(path=resolved.optimize_settings_file)
        rate_limit_manager = RateLimitManager(
            state_path=resolved.rate_limit_state_file,
            registry=mmos_registry,
        )
        _opt_settings = mmos_settings.get()
        routing_engine = RoutingEngine(
            registry=mmos_registry,
            rate_limit_manager=rate_limit_manager,
            settings=_opt_settings,
            rules_loader=RoutingRulesLoader(path=resolved.routing_rules_file),
            classifier=IntentClassifier(),
        )
        context_engine = ContextRelevanceEngine(
            settings=_opt_settings,
            embedding_backend=emb,
        )
        plan_engine = PlanEngine(
            registry=mmos_registry,
            rate_limit_manager=rate_limit_manager,
            settings=_opt_settings,
        )
        plan_runner = PlanRunner(
            registry=mmos_registry,
            rate_limit_manager=rate_limit_manager,
            plans_dir=resolved.plans_dir,
        )
        mixing_orchestrator = MixingOrchestrator(
            registry=mmos_registry,
            rate_limit_manager=rate_limit_manager,
            settings=_opt_settings,
            plan_engine=plan_engine,
            plan_runner=plan_runner,
        )

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
            search_cache=search_cache,
            search_orchestrator=search_orchestrator,
            plugin_manager=PluginManager(),
            rag_manager=rag_manager,
            embedding_registry=embedding_registry,
            tool_runner=tool_runner,
            mcp_manager=mcp_manager,
            notifier=notifier,
            spend_tracker=spend_tracker,
            template_manager=TemplateManager(path=resolved.templates_file),
            schedule_manager=ScheduleManager(path=resolved.schedules_file),
            debug_manager=debug_manager,
            mmos_registry=mmos_registry,
            mmos_settings=mmos_settings,
            rate_limit_manager=rate_limit_manager,
            routing_engine=routing_engine,
            context_engine=context_engine,
            plan_engine=plan_engine,
            plan_runner=plan_runner,
            mixing_orchestrator=mixing_orchestrator,
        )
