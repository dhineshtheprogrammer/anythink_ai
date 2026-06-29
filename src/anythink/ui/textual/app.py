"""Textual application shell — Simple Chat Mode and 4-panel Dashboard Mode."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Input, TabbedContent, TabPane

from anythink import __version__
from anythink.app.chat import (
    ChatState,
    _build_session,
    _freshness_to_date,
    _history_context,
    _inject_search_context,
    _trim_history,
)
from anythink.bookmarks.manager import BookmarkManager
from anythink.branch.manager import BranchManager
from anythink.commands.registry import CommandRegistry
from anythink.exceptions import AnythinkError, RAGError, SearchError, ToolExecutionError, VoiceError
from anythink.files.reader import ImageAttachment, TextAttachment
from anythink.notify.notifier import SLOW_EXEC_S, SLOW_RESPONSE_S
from anythink.providers.base import ChatMessage, ContentPart, TextPart
from anythink.session.manager import auto_session_name
from anythink.ui.banner import _BANNER
from anythink.ui.bubbles import AIBubble, CompactNotice, LogoBubble, SystemBubble, UserBubble
from anythink.ui.hud import HUDWidget
from anythink.ui.icons import get_icon, patch_rich_cell_len
from anythink.ui.startup import (
    apply_icon_style_heuristic,
    find_resumable_session,
    is_returning_user,
)
from anythink.ui.textual.conversation import ConversationView
from anythink.ui.textual.hint_bar import HintBar
from anythink.ui.textual.input_area import InputArea
from anythink.ui.textual.microprompt import MicroPromptWidget
from anythink.ui.textual.override_caution_modal import OverrideCautionModal
from anythink.ui.textual.panels.debug_panel import DebugPanel
from anythink.ui.textual.panels.file_browser import FileBrowserTab
from anythink.ui.textual.panels.optimize_panel import OptimizePanel
from anythink.ui.textual.panels.phase_tracker import PhaseTrackerPanel
from anythink.ui.textual.panels.plan_review_panel import PlanReviewPanel
from anythink.ui.textual.panels.rag_browser import RAGBrowserTab
from anythink.ui.textual.panels.ratelimit_panel import RateLimitPanel
from anythink.ui.textual.panels.session_list import SessionListPanel
from anythink.ui.textual.panels.stats import StatsPanel
from anythink.ui.textual.panels.tool_output import ToolOutputTab
from anythink.ui.textual.rag_settings import RAGSettingsMenu
from anythink.ui.textual.rag_wizard import RAGIndexWizard
from anythink.ui.textual.settings_menu import SettingsMenu
from anythink.ui.textual.theme_bridge import resolve, theme_css_vars
from anythink.ui.textual.thinking_widget import ThinkingWidget
from anythink.ui.textual.tips_bar import TipsBar

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.session.models import Session as _Session

_INPUT_PLACEHOLDER_DEFAULT = "Type a message… (/help for commands)"
_INPUT_PLACEHOLDER_NAMING = "Session name  (Enter = auto-name)"


class AnythinkApp(App[int]):
    """Simple Chat Mode + optional 4-panel Dashboard Mode.

    Layout (always composed; dashboard panels hidden by default):

        ┌──────────────── HUD (docked top) ─────────────────┐
        │ LeftPanel  │   ConversationView   │  StatsPanel    │
        ├────────────┴──────────────────────┴────────────────┤
        │  BottomTabs: Files | RAG | Tool Output             │
        ├────────────────────────────────────────────────────┤
        │  InputArea (docked bottom)                         │
        └────────────────────────────────────────────────────┘

    Ctrl+D toggles Dashboard / Simple; Ctrl+L / Ctrl+R toggle side panels.
    """

    BINDINGS = [
        Binding("ctrl+d", "toggle_dashboard", "Toggle Dashboard", show=True, priority=True),
        Binding("ctrl+l", "toggle_left_panel", "Sessions", show=False, priority=True),
        Binding("ctrl+r", "toggle_right_panel", "Stats", show=False, priority=True),
        Binding("ctrl+b", "toggle_debug_panel", "Debug Panel", show=False, priority=True),
        Binding("escape", "escape_or_stop", "Stop / Focus", show=False, priority=True),
        Binding("ctrl+y", "copy_response", "Copy response", show=False),
        Binding("ctrl+k", "copy_last_code", "Copy code", show=False),
        Binding("ctrl+o", "open_in_editor", "Open in editor", show=False),
    ]

    DEFAULT_CSS = """
    Screen {
        layout: vertical;
    }
    HUDWidget {
        height: 3;
        dock: top;
        padding: 0 1;
    }
    #content-row {
        height: 1fr;
    }
    ConversationView {
        width: 1fr;
        height: 100%;
    }
    SessionListPanel {
        width: 24;
        display: none;
    }
    StatsPanel {
        width: 28;
        display: none;
    }
    DebugPanel {
        width: 32;
        display: none;
    }
    #bottom-tabs {
        height: 10;
        display: none;
    }
    InputArea {
        dock: bottom;
        height: auto;
        max-height: 8;
    }
    """

    def get_css_variables(self) -> dict[str, str]:
        """Inject per-theme CSS variables so $accent, $background etc. follow the theme.

        Merges with Textual's built-in variables so $foreground and other
        framework-level vars remain available.
        """
        base = super().get_css_variables()
        base.update(theme_css_vars(self._ctx.theme))
        return base

    def __init__(self, ctx: AppContext, *, dashboard: bool = False) -> None:
        self._ctx = ctx  # set before super().__init__() so get_css_variables() can read it
        super().__init__()
        self._state: ChatState | None = None
        self._cmd_registry: CommandRegistry = CommandRegistry.from_entry_points()
        self._dashboard_mode: bool = dashboard

        # ── Phase 2 state ──────────────────────────────────────────────────
        self._pending_resume: _Session | None = None
        self._naming_mode: bool = False
        self._pending_undo: bool = False
        self._bubble_pairs: list[tuple[Widget, Widget]] = []
        self._undo_checkpoints: list[int] = []
        self._turn_bubbles: dict[int, AIBubble] = {}

        # ── Phase 3 state ──────────────────────────────────────────────────
        self._pending_branch_create: bool = False

        # ── Phase 5 state ──────────────────────────────────────────────────
        self._pending_exec_data: dict[str, str] | None = None
        self._pending_browse_data: dict[str, str] | None = None

        # ── Phase 6 state ──────────────────────────────────────────────────
        self._pending_mcp_data: dict[str, str] | None = None

        # ── Phase 8 state ──────────────────────────────────────────────────
        self._pending_voice: bool = False
        self._voice_recorder: Any = None  # VoiceRecorder | None

        # ── V2.1 state ─────────────────────────────────────────────────────
        self._pending_clear: bool = False
        self._stop_streaming: bool = False
        self._active_ai_bubble: AIBubble | None = None
        self._last_response_text: str = ""
        self._naming_prompt_bubble: SystemBubble | None = None

        # ── RAG Phase 6 state ──────────────────────────────────────────────
        # No-match: set when retrieved chunks all fall below threshold
        self._pending_rag_nomatch: dict | None = None
        # Override confirm: set when user picks option [2] (show chunks → y/n)
        self._pending_rag_override_confirm: dict | None = None

        # ── RAG Phase 7 state ──────────────────────────────────────────────
        self._rag_wizard: RAGIndexWizard | None = None

        # ── V3 state ───────────────────────────────────────────────────────
        # Compare mode: aliases set by /compare; cleared once comparison fires
        self._pending_compare_aliases: list[str] | None = None
        # Results from a completed comparison; cleared once user picks
        self._pending_compare_results: list[Any] | None = None
        self._pending_compare_pick: bool = False
        # Update confirm: set by /update when a newer version is available
        self._pending_update: bool = False

        # ── V4 MMOS state ──────────────────────────────────────────────────
        import asyncio as _asyncio

        self._microprompt_event: _asyncio.Event = _asyncio.Event()
        self._microprompt_result: Any = None  # QueryIntent | None
        self._plan_approval_event: _asyncio.Event = _asyncio.Event()
        self._plan_approval_result: bool = False
        self._plan_abort_signal: _asyncio.Event = _asyncio.Event()
        self._override_confirm_event: _asyncio.Event = _asyncio.Event()
        self._override_proceed: bool = False
        self._pending_optimize_reset: bool = False

    # ── widget tree ────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield HUDWidget(self._ctx.theme, __version__, id="hud")
        with Horizontal(id="content-row"):
            yield SessionListPanel(self._ctx, id="left-panel")
            yield ConversationView()
            yield StatsPanel(self._ctx, id="right-panel")
            yield DebugPanel(id="debug-panel")
        with TabbedContent(id="bottom-tabs"):
            with TabPane("Files", id="tab-files"):
                yield FileBrowserTab(id="file-browser")
            with TabPane("RAG", id="tab-rag"):
                yield RAGBrowserTab(self._ctx, id="rag-browser")
            with TabPane("Tools", id="tab-tools"):
                yield ToolOutputTab(id="tool-output")
        yield SettingsMenu(self._ctx, self._ctx.theme, id="settings-menu")
        yield RAGSettingsMenu(self._ctx, self._ctx.theme, id="rag-settings-menu")
        yield OptimizePanel(self._ctx, self._ctx.theme, id="optimize-panel")
        yield RateLimitPanel(id="ratelimit-panel")
        yield PlanReviewPanel(id="plan-review-panel")
        yield PhaseTrackerPanel(id="phase-tracker-panel")
        yield MicroPromptWidget(id="microprompt")
        yield OverrideCautionModal(id="override-caution")
        yield TipsBar(self._ctx.theme, id="tips-bar")
        yield InputArea()
        yield HintBar(self._ctx.theme, id="hint-bar")

    def on_mount(self) -> None:
        """Resolve state, populate HUD, show startup/resume UI, and focus input."""
        patch_rich_cell_len()
        apply_icon_style_heuristic(self._ctx)
        t = self._ctx.theme
        ia = self.query_one(InputArea)
        ia.styles.border_top = ("solid", resolve(t.muted))
        ia.configure(list(self._cmd_registry.all_commands()), t)
        self.query_one(Input).focus()

        # Apply per-theme background fill to the screen and conversation area
        self._apply_theme_background(t)

        if self._dashboard_mode:
            self._apply_dashboard_layout(True)

        # Start the 60-second timestamp refresh ticker
        self.set_interval(60, self._tick_timestamps)

        from anythink.app.chat import ChatApp

        chat_app = ChatApp(self._ctx, self._cmd_registry)
        self._state = chat_app._resolve_state()

        conv = self.query_one(ConversationView)
        hud = self.query_one(HUDWidget)

        # Show ASCII logo on every launch
        tagline = f"Think anything. Ask anything.  •  v{__version__}"
        conv.add_bubble(LogoBubble(_BANNER, tagline, t))

        if self._state is None:
            conv.add_bubble(
                SystemBubble(
                    "No model configured. Run `anythink model add` to get started.",
                    t,
                    kind="error",
                    config=self._ctx.config,
                )
            )
            return

        hud.update_from_state(self._ctx, self._state)

        # Session resume takes priority over naming
        if is_returning_user(self._ctx):
            resumable = find_resumable_session(self._ctx)
            if resumable:
                self._pending_resume = resumable
                label = resumable.name or resumable.id[:8] + "…"
                conv.add_bubble(
                    SystemBubble(
                        f'↩ Resume last session? "{label}"  [Y/n]',
                        t,
                        kind="info",
                        config=self._ctx.config,
                    )
                )
                return  # skip naming prompt while resume is pending

        # First-launch naming prompt
        self._naming_mode = True
        inp = self.query_one(Input)
        inp.placeholder = _INPUT_PLACEHOLDER_NAMING
        naming_bubble = SystemBubble(
            "Name this session?  (press Enter to auto-name)",
            t,
            kind="info",
            config=self._ctx.config,
        )
        self._naming_prompt_bubble = naming_bubble
        conv.add_bubble(naming_bubble)

    # ── message handlers ───────────────────────────────────────────────────

    async def on_input_area_submitted(self, event: InputArea.Submitted) -> None:
        """Route input through any pending interactive mode, then chat."""
        text = event.text

        # ── session resume ─────────────────────────────────────────────────
        if self._pending_resume is not None:
            await self._handle_resume_response(text)
            return

        # ── session naming ─────────────────────────────────────────────────
        if self._naming_mode:
            await self._handle_session_naming(text)
            return

        # ── undo confirmation ──────────────────────────────────────────────
        if self._pending_undo:
            await self._handle_undo_confirmation(text)
            return

        # ── RAG no-match 3-option flow ─────────────────────────────────────
        if self._pending_rag_nomatch is not None:
            await self._handle_rag_nomatch(text)
            return

        # ── RAG override confirm (option 2 → y/n) ──────────────────────────
        if self._pending_rag_override_confirm is not None:
            await self._handle_rag_override_confirm(text)
            return

        # ── RAG index wizard ───────────────────────────────────────────────
        if self._rag_wizard is not None and self._rag_wizard.is_active:
            await self._handle_rag_wizard_step(text)
            return

        # ── branch create confirmation ─────────────────────────────────────
        if self._pending_branch_create:
            await self._handle_branch_confirmation(text)
            return

        # ── exec approval ──────────────────────────────────────────────────
        if self._pending_exec_data is not None:
            await self._handle_exec_confirmation(text)
            return

        # ── browse approval ────────────────────────────────────────────────
        if self._pending_browse_data is not None:
            await self._handle_browse_confirmation(text)
            return

        # ── MCP tool call approval ─────────────────────────────────────────
        if self._pending_mcp_data is not None:
            await self._handle_mcp_confirmation(text)
            return

        # ── voice recording stop ────────────────────────────────────────────
        if self._pending_voice:
            self._pending_voice = False
            self.run_worker(
                self._finish_voice_recording(),
                exclusive=False,
                exit_on_error=False,
            )
            return

        # ── clear confirmation ─────────────────────────────────────────────
        if self._pending_clear:
            await self._handle_clear_confirmation(text)
            return

        # ── compare pick ───────────────────────────────────────────────────
        if self._pending_compare_pick:
            await self._handle_compare_pick(text)
            return

        # ── update confirm ─────────────────────────────────────────────────
        if self._pending_update:
            await self._handle_update_confirmation(text)
            return

        # ── optimize reset confirmation ────────────────────────────────────
        if self._pending_optimize_reset:
            self._pending_optimize_reset = False
            if text.strip().lower() in ("y", "yes"):
                self._ctx.mmos_settings.reset()
                self._sync_mmos_hud()
                conv = self.query_one(ConversationView)
                conv.add_bubble(
                    SystemBubble(
                        "Optimization settings reset to defaults.",
                        self._ctx.theme,
                        kind="info",
                    )
                )
            return

        if not text or self._state is None:
            return

        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        if text.startswith("/"):
            conv.add_bubble(UserBubble(text, t, config=self._ctx.config))
            await self._dispatch_command(text)
            return

        if text.lower() in ("exit", "quit"):
            self.exit(0)
            return

        state = self._state

        # ── compare mode: intercept next message ───────────────────────────
        if self._pending_compare_aliases is not None:
            aliases = self._pending_compare_aliases
            self._pending_compare_aliases = None
            conv.add_bubble(UserBubble(text, t, config=self._ctx.config))
            conv.add_bubble(
                SystemBubble(
                    f"Comparing {len(aliases)} models for this prompt…",
                    t,
                    kind="info",
                )
            )
            self.run_worker(
                self._run_comparison(state, text, aliases),
                exclusive=False,
                exit_on_error=False,
            )
            return

        # ── V4 MMOS query pipeline ─────────────────────────────────────────
        if self._ctx.config.mmos_enabled:
            conv.add_bubble(UserBubble(text, t, config=self._ctx.config))
            self.run_worker(
                self._run_mmos_query(state, text),
                exclusive=False,
                exit_on_error=False,
            )
            return

        extra: list[ContentPart] = []

        for att in state.pending_attachments:
            if isinstance(att, TextAttachment):
                extra.append(TextPart(f"[File: {att.filename}]\n{att.content}"))
            elif isinstance(att, ImageAttachment):
                extra.append(att.image_part)
        state.pending_attachments.clear()

        # Record checkpoint BEFORE appending user message (for undo)
        self._undo_checkpoints.append(len(state.history))

        if extra:
            extra.append(TextPart(text))
            user_msg = ChatMessage(role="user", content=extra)
        else:
            user_msg = ChatMessage(role="user", content=text)
        state.history.append(user_msg)

        user_bub = UserBubble(text, t, config=self._ctx.config)
        conv.add_bubble(user_bub)

        # ThinkingWidget is a temporary placeholder; _stream_response replaces it
        thinking = ThinkingWidget(t)
        conv.add_bubble(thinking)

        bubble = AIBubble(
            t,
            model_alias=state.model_id,
            provider=state.provider.display_name,
            config=self._ctx.config,
        )
        self._bubble_pairs.append((user_bub, bubble))

        import contextlib

        with contextlib.suppress(Exception):
            self.query_one(TipsBar).start()

        self.run_worker(
            self._stream_response(state, bubble, text, thinking=thinking),
            exclusive=False,
            exit_on_error=False,
        )

    # ── dashboard actions ──────────────────────────────────────────────────

    def _apply_dashboard_layout(self, enabled: bool) -> None:
        """Show or hide all dashboard panels without recomposing."""
        self.query_one("#left-panel").display = enabled
        self.query_one("#right-panel").display = enabled
        self.query_one("#bottom-tabs").display = enabled
        if enabled:
            active_id = self._state.session_id if self._state else ""
            self.query_one(SessionListPanel).refresh_sessions(active_id)
            self.query_one(StatsPanel).update_stats(self._ctx, self._state)
            self.query_one(RAGBrowserTab).refresh_index_list()

    def action_toggle_dashboard(self) -> None:
        """Ctrl+D: flip between Simple and Dashboard mode."""
        self._dashboard_mode = not self._dashboard_mode
        self._apply_dashboard_layout(self._dashboard_mode)
        t = self._ctx.theme
        conv = self.query_one(ConversationView)
        label = "Dashboard" if self._dashboard_mode else "Simple Chat"
        conv.add_bubble(SystemBubble(f"Switched to {label} mode.", t, kind="info"))

    def action_toggle_left_panel(self) -> None:
        """Ctrl+L: show/hide the Sessions panel (dashboard mode only)."""
        if not self._dashboard_mode:
            return
        lp = self.query_one("#left-panel")
        lp.display = not lp.display
        if lp.display:
            active_id = self._state.session_id if self._state else ""
            self.query_one(SessionListPanel).refresh_sessions(active_id)

    def action_toggle_right_panel(self) -> None:
        """Ctrl+R: show/hide the Stats panel (dashboard mode only)."""
        if not self._dashboard_mode:
            return
        rp = self.query_one("#right-panel")
        rp.display = not rp.display
        if rp.display:
            self.query_one(StatsPanel).update_stats(self._ctx, self._state)

    def action_toggle_debug_panel(self) -> None:
        """Ctrl+B: show/hide the Debug Panel."""
        self._toggle_debug_panel()

    def _toggle_debug_panel(self) -> None:
        """Show or hide the debug side panel and sync DebugManager state."""
        import contextlib

        dm = self._ctx.debug_manager
        new_state = dm.toggle_panel()
        with contextlib.suppress(Exception):
            dp = self.query_one("#debug-panel")
            dp.display = new_state
            if new_state:
                self.query_one(DebugPanel).set_level(dm.level())

    async def _stream_replay(self, rec: object, provider_alias: str | None) -> None:
        """Background worker: replay a past request and show the response."""
        import contextlib

        if self._state is None:
            return

        from anythink.debug.models import RequestDebugRecord
        from anythink.providers.base import ChatMessage

        assert isinstance(rec, RequestDebugRecord)

        conv = self.query_one(ConversationView)
        t = self._ctx.theme
        state = self._state

        provider = state.provider
        if provider_alias:
            with contextlib.suppress(Exception):
                alias_obj = self._ctx.model_registry.get(provider_alias)
                if alias_obj is not None:
                    api_key = self._ctx.key_manager.get_key(alias_obj.provider)
                    candidate = self._ctx.provider_registry.instantiate(
                        alias_obj.provider,
                        api_key=api_key,
                        base_url=self._ctx.config.local_servers.get(alias_obj.provider),
                    )
                    if candidate is not None:
                        provider = candidate

        messages = []
        for item in rec.prompt_payload:
            role = item.get("role", "user")
            content = item.get("content", "")
            if isinstance(content, str):
                messages.append(ChatMessage(role=role, content=content))

        bubble = AIBubble(
            t,
            model_alias=f"↺ Replay #{rec.request_id}",
            provider=provider.display_name,
            config=self._ctx.config,
        )
        conv.add_bubble(bubble)

        buffer = ""
        with contextlib.suppress(Exception):
            self.query_one(HintBar).set_streaming(True)
        try:
            chunk_stream = provider.stream_chat(
                messages=messages,
                model=rec.model_id,
                gen_params=rec.gen_params,
            )
            async for chunk in chunk_stream:
                if self._stop_streaming:
                    break
                if chunk.text:
                    buffer += chunk.text
                    bubble.append_text(chunk.text)
        except Exception as exc:
            bubble.show_error(str(exc))
        finally:
            bubble.finalize(buffer)
            with contextlib.suppress(Exception):
                self.query_one(HintBar).set_streaming(False)

    def action_escape_or_stop(self) -> None:
        """Escape: close settings if open; stop streaming if active; else focus input."""
        import contextlib

        # RAG settings overlay — close if open
        with contextlib.suppress(Exception):
            rsm = self.query_one(RAGSettingsMenu)
            if rsm.is_open():
                rsm.action_close()
                return

        # Cancel active RAG wizard
        if self._rag_wizard is not None and self._rag_wizard.is_active:
            self._rag_wizard.cancel()
            self._rag_wizard = None
            with contextlib.suppress(Exception):
                conv = self.query_one(ConversationView)
                conv.add_bubble(
                    SystemBubble("Wizard cancelled.", self._ctx.theme, kind="info")
                )
            return

        # Settings overlay takes highest priority
        with contextlib.suppress(Exception):
            sm = self.query_one(SettingsMenu)
            if sm.is_open():
                sm.action_close()
                return

        # V4: Optimize panel
        with contextlib.suppress(Exception):
            op = self.query_one(OptimizePanel)
            if op.is_open():
                op.action_close()
                return

        # Next: abort an in-progress generation
        if self._active_ai_bubble is not None and not self._stop_streaming:
            self._stop_streaming = True
            return

        # Fallback: restore focus to the chat input
        self.query_one(Input).focus()

    def action_copy_response(self) -> None:
        """Ctrl+Y: copy the last AI response to the system clipboard."""
        import contextlib

        conv = self.query_one(ConversationView)
        t = self._ctx.theme
        if not self._last_response_text:
            conv.add_bubble(SystemBubble("No response to copy yet.", t, kind="info"))
            return
        try:
            import pyperclip

            pyperclip.copy(self._last_response_text)
            conv.add_bubble(SystemBubble("✓ Response copied to clipboard.", t, kind="success"))
        except Exception as exc:
            with contextlib.suppress(Exception):
                conv.add_bubble(SystemBubble(f"Clipboard unavailable: {exc}", t, kind="error"))

    def action_copy_last_code(self) -> None:
        """Ctrl+K: copy the first code block from the last AI response."""
        import contextlib
        import re

        conv = self.query_one(ConversationView)
        t = self._ctx.theme
        if not self._last_response_text:
            conv.add_bubble(SystemBubble("No response to copy yet.", t, kind="info"))
            return
        match = re.search(r"```[^\n]*\n(.*?)```", self._last_response_text, re.DOTALL)
        if not match:
            conv.add_bubble(SystemBubble("No code block found in last response.", t, kind="info"))
            return
        try:
            import pyperclip

            pyperclip.copy(match.group(1))
            conv.add_bubble(SystemBubble("✓ Code copied to clipboard.", t, kind="success"))
        except Exception as exc:
            with contextlib.suppress(Exception):
                conv.add_bubble(SystemBubble(f"Clipboard unavailable: {exc}", t, kind="error"))

    def action_open_in_editor(self) -> None:
        """Ctrl+O: open the current session file in the system text editor."""
        import subprocess  # nosec B404
        import sys

        conv = self.query_one(ConversationView)
        t = self._ctx.theme
        if self._state is None:
            conv.add_bubble(SystemBubble("No active session.", t, kind="info"))
            return
        path = self._ctx.paths.sessions_dir / f"{self._state.session_id}.yaml"
        if not path.exists():
            conv.add_bubble(
                SystemBubble(
                    "Session file not yet saved. Send a message first.",
                    t,
                    kind="info",
                )
            )
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(["notepad.exe", str(path)])  # nosec B603, B607
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])  # nosec B603, B607
            else:
                subprocess.Popen(["xdg-open", str(path)])  # nosec B603, B607
            conv.add_bubble(SystemBubble("Session file opened in editor.", t, kind="success"))
        except Exception as exc:
            conv.add_bubble(SystemBubble(f"Could not open editor: {exc}", t, kind="error"))

    def on_settings_menu_changed(self, event: SettingsMenu.Changed) -> None:
        """Sync runtime state immediately when a config value is saved from settings."""
        if event.field == "search_default_enabled" and self._state is not None:
            self._state.search_enabled = self._ctx.config.search_default_enabled

        if event.field == "active_theme":
            from anythink.ui.theme import get_theme

            new_theme = get_theme(self._ctx.config.active_theme)
            self._ctx.theme = new_theme
            self.query_one(HUDWidget).refresh_theme(new_theme)
            # Update CSS variables and refresh screen background
            self.refresh_css()
            self._apply_theme_background(new_theme)

        if self._state is not None:
            self.query_one(HUDWidget).update_from_state(self._ctx, self._state)

        # Retroactively re-render all visual elements on any appearance change
        _VISUAL_FIELDS = {
            "active_theme",
            "bubble_style",
            "density",
            "show_avatars",
            "timestamps",
            "icon_style",
        }
        if event.field in _VISUAL_FIELDS:
            self._refresh_all_bubbles()

        # Update tips bar icon style
        if event.field == "icon_style":
            import contextlib

            with contextlib.suppress(Exception):
                self.query_one(TipsBar).set_config(self._ctx.config)

    def on_click(self, event: object) -> None:  # type: ignore[override]
        """Redirect any click on a non-interactive area to the chat input.

        Interactive overlay panels retain their own focus when open.
        The Input widget stops its own click events, so this only fires
        for clicks on read-only areas (conversation, HUD, side panels, etc.).
        """
        import contextlib

        # Don't steal focus while an interactive overlay is visible
        for panel_id in (
            "settings-menu",
            "rag-settings-menu",
            "optimize-panel",
            "ratelimit-panel",
            "plan-review-panel",
            "phase-tracker-panel",
            "microprompt",
            "override-caution",
        ):
            with contextlib.suppress(Exception):
                widget = self.query_one(f"#{panel_id}")
                if widget.display:
                    return

        with contextlib.suppress(Exception):
            self.query_one(Input).focus()

    def on_settings_menu_closed(self, event: SettingsMenu.Closed) -> None:
        """Return focus to the input after the settings overlay is dismissed."""
        self.query_one(Input).focus()
        if self._state is not None:
            # Final sync: ensure runtime state matches whatever was saved
            self._state.search_enabled = self._ctx.config.search_default_enabled
            self.query_one(HUDWidget).update_from_state(self._ctx, self._state)

    # ── V2.2 visual helpers ────────────────────────────────────────────────────

    def _apply_theme_background(self, theme: object) -> None:
        """Set Screen and ConversationView background to the theme's tinted canvas."""
        import contextlib

        from anythink.ui.theme import Theme as _Theme

        if not isinstance(theme, _Theme):
            return
        bg = theme.background
        with contextlib.suppress(Exception):
            self.screen.styles.background = bg
        with contextlib.suppress(Exception):
            self.query_one(ConversationView).styles.background = bg

    def _refresh_all_bubbles(self) -> None:
        """Retroactively re-render every visible bubble with the current theme and config."""
        import contextlib

        t = self._ctx.theme
        cfg = self._ctx.config
        bubble_types = (UserBubble, AIBubble, SystemBubble, LogoBubble, CompactNotice)
        _selector = "UserBubble, AIBubble, SystemBubble, LogoBubble, CompactNotice"
        with contextlib.suppress(Exception):
            for bubble in self.query(_selector):
                if isinstance(bubble, bubble_types) and hasattr(bubble, "refresh_visual"):
                    bubble.refresh_visual(t, cfg)

    def _tick_timestamps(self) -> None:
        """Called every 60 s to update relative timestamps on all visible bubbles."""
        import contextlib

        with contextlib.suppress(Exception):
            for bubble in self.query("UserBubble, AIBubble"):
                if hasattr(bubble, "refresh_timestamp"):
                    bubble.refresh_timestamp()

    def on_session_list_panel_session_selected(
        self, event: SessionListPanel.SessionSelected
    ) -> None:
        """Load the session the user clicked in the Sessions panel."""
        if self._state is None:
            return
        session = self._ctx.session_manager.find_by_name_or_id(event.session_id)
        if session is None:
            return
        state = self._state
        state.history = list(session.messages)
        state.bookmarks = list(session.bookmarks)
        state.session_id = session.id
        state.session_name = session.name
        state.total_tokens_used = 0
        state.active_branch = "main"
        state.branches = {"main": state.history}
        state.branch_bookmarks = {"main": state.bookmarks}
        state.branch_diverges = {"main": 0}

        # Rebuild conversation view
        conv = self.query_one(ConversationView)
        self.run_worker(
            self._reload_conversation(conv, state, session.name or session.id[:8]),
            exclusive=False,
            exit_on_error=False,
        )

    async def _reload_conversation(
        self, conv: ConversationView, state: ChatState, label: str
    ) -> None:
        """Redraw the conversation view with the newly loaded session."""
        for child in list(conv.children):
            await child.remove()
        self._bubble_pairs.clear()
        self._undo_checkpoints.clear()
        self._turn_bubbles.clear()

        t = self._ctx.theme
        non_sys = [m for m in state.history if m.role != "system"]
        for i in range(0, len(non_sys), 2):
            user_msg = non_sys[i]
            u_text = user_msg.content if isinstance(user_msg.content, str) else "…"
            user_bub = UserBubble(u_text, t, config=self._ctx.config)
            await conv.mount(user_bub)
            if i + 1 < len(non_sys):
                ai_msg = non_sys[i + 1]
                a_text = ai_msg.content if isinstance(ai_msg.content, str) else "…"
                ai_bub = AIBubble(
                    t,
                    model_alias=state.model_id,
                    provider=state.provider.display_name,
                    config=self._ctx.config,
                )
                ai_bub.finalize(a_text)
                await conv.mount(ai_bub)
                self._bubble_pairs.append((user_bub, ai_bub))
                self._undo_checkpoints.append(i)

        conv.scroll_end(animate=False)
        conv.add_bubble(SystemBubble(f'Loaded session "{label}".', t, kind="success"))
        self.query_one(HUDWidget).update_from_state(self._ctx, state)
        if self._dashboard_mode:
            active_id = state.session_id
            self.query_one(SessionListPanel).refresh_sessions(active_id)
            self.query_one(StatsPanel).update_stats(self._ctx, state)

    def _log_tool_event(self, tool_name: str, kind: str, summary: str) -> None:
        """Append an event to the Tool Output tab (best-effort)."""
        import contextlib

        with contextlib.suppress(Exception):
            self.query_one(ToolOutputTab).add_event(tool_name, kind, summary)

    def _log_tool_debug(
        self,
        name: str,
        args: dict[str, object],
        result_summary: str,
        duration_s: float,
        success: bool,
    ) -> None:
        """Record a tool call into the current debug record (best-effort)."""
        dm = self._ctx.debug_manager
        if not dm.is_active():
            return
        rec = dm.latest()
        if rec is None:
            return
        import contextlib

        with contextlib.suppress(Exception):
            from anythink.debug.models import ToolCallEntry

            rec.tool_calls.append(
                ToolCallEntry(
                    name=name,
                    arguments=dict(args),
                    result_summary=result_summary,
                    duration_s=duration_s,
                    success=success,
                )
            )

    # Maximum number of turn-pairs tracked for undo / bookmarks.
    # Beyond this, the oldest entries are pruned to bound memory usage in
    # very long sessions without affecting the visible conversation.
    _MAX_TRACKED_TURNS = 500

    def _prune_history_tracking(self) -> None:
        """Cap in-memory tracking lists to avoid unbounded growth."""
        if len(self._bubble_pairs) > self._MAX_TRACKED_TURNS:
            trim = len(self._bubble_pairs) - self._MAX_TRACKED_TURNS
            self._bubble_pairs = self._bubble_pairs[trim:]
            self._undo_checkpoints = self._undo_checkpoints[trim:]
        if len(self._turn_bubbles) > self._MAX_TRACKED_TURNS:
            oldest = sorted(self._turn_bubbles)[:50]
            for k in oldest:
                del self._turn_bubbles[k]

    def _refresh_dashboard_panels(self) -> None:
        """Refresh side panels if dashboard mode is active (best-effort)."""
        if not self._dashboard_mode:
            return
        import contextlib

        with contextlib.suppress(Exception):
            active_id = self._state.session_id if self._state else ""
            self.query_one(SessionListPanel).refresh_sessions(active_id)
            self.query_one(StatsPanel).update_stats(self._ctx, self._state)

    # ── interactive mode handlers ──────────────────────────────────────────

    async def _handle_resume_response(self, text: str) -> None:
        """Handle Y/N answer to the session-resume prompt."""
        conv = self.query_one(ConversationView)
        t = self._ctx.theme
        session = self._pending_resume
        self._pending_resume = None

        if text.lower() in ("y", "yes", ""):
            if session is not None and self._state is not None:
                self._state.history = list(session.messages)
                self._state.session_id = session.id
                self._state.session_name = session.name
                self._state.bookmarks = list(session.bookmarks)
                self._state.total_tokens_used = 0
                label = session.name or session.id[:8] + "…"
                conv.add_bubble(
                    SystemBubble(
                        f'Resumed session "{label}" ({len(session.messages)} messages).',
                        t,
                        kind="success",
                    )
                )
                self.query_one(HUDWidget).update_from_state(self._ctx, self._state)
        else:
            conv.add_bubble(SystemBubble("Starting new session.", t, kind="info"))
            # Show naming prompt after declining resume
            self._naming_mode = True
            self.query_one(Input).placeholder = _INPUT_PLACEHOLDER_NAMING

    async def _handle_session_naming(self, text: str) -> None:
        """Process the session name response."""
        if self._state is None:
            return
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        typed = text.strip()
        auto = not bool(typed)
        name = typed if typed else auto_session_name(self._state.model_id)
        self._state.session_name = name
        self._naming_mode = False
        self.query_one(Input).placeholder = _INPUT_PLACEHOLDER_DEFAULT
        self.query_one(HUDWidget).update_from_state(self._ctx, self._state)

        # Remove the prompt bubble and show a single compact confirmation line
        if self._naming_prompt_bubble is not None:
            await self._naming_prompt_bubble.remove()
            self._naming_prompt_bubble = None

        suffix = "  (auto)" if auto else ""
        conv.add_bubble(
            CompactNotice(
                f'Session named: "{name}"{suffix}',
                t,
                config=self._ctx.config,
            )
        )

    async def _handle_undo_confirmation(self, text: str) -> None:
        """Execute undo if confirmed, or cancel."""
        self._pending_undo = False
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        if text.lower() in ("y", "yes"):
            await self._perform_undo()
        else:
            conv.add_bubble(SystemBubble("Undo cancelled.", t, kind="info"))

    async def _perform_undo(self) -> None:
        """Remove the last exchange from history, bubbles, and the saved file."""
        if self._state is None:
            return
        state = self._state
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        if not self._undo_checkpoints:
            conv.add_bubble(SystemBubble("Nothing to undo.", t, kind="info"))
            return

        # Truncate history to the checkpoint before the last exchange
        checkpoint = self._undo_checkpoints.pop()
        state.history = state.history[:checkpoint]
        state.total_tokens_used = 0  # conservative reset

        # Remove the last bubble pair from the DOM
        if self._bubble_pairs:
            user_bub, ai_bub = self._bubble_pairs.pop()
            await user_bub.remove()
            await ai_bub.remove()

        # Resave using full branch-aware builder
        if self._ctx.config.session_autosave:
            self._ctx.session_manager.save(_build_session(state))

        self.query_one(HUDWidget).update_from_state(self._ctx, state)
        conv.add_bubble(SystemBubble("Last exchange undone.", t, kind="success"))

    async def _handle_branch_confirmation(self, text: str) -> None:
        """Execute branch creation if confirmed, or cancel."""
        self._pending_branch_create = False
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        if text.lower() not in ("y", "yes"):
            conv.add_bubble(SystemBubble("Branch creation cancelled.", t, kind="info"))
            return

        if self._state is None:
            return

        bm = BranchManager(self._state)
        name = bm.create_branch()
        # Reset per-branch tracking
        self._undo_checkpoints.clear()
        self._bubble_pairs.clear()
        # Update HUD branch indicator
        hud = self.query_one(HUDWidget)
        hud.branch = name
        hud.update_from_state(self._ctx, self._state)
        diverge_turn = self._state.branch_diverges.get(name, 0)
        conv.add_bubble(
            SystemBubble(
                f"🌿 Created {name!r} from Turn {diverge_turn}. "
                "New messages go into this branch.",
                t,
                kind="success",
            )
        )

    async def _handle_clear_confirmation(self, text: str) -> None:
        """Hard-reset the visible conversation if the user confirms."""
        self._pending_clear = False
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        if text.lower() not in ("y", "yes"):
            conv.add_bubble(SystemBubble("Clear cancelled.", t, kind="info"))
            return

        if self._state is None:
            return

        state = self._state

        # Save conversation to disk before wiping visible state
        if state.history:
            self._ctx.session_manager.save(_build_session(state))

        # Reset in-memory history to system messages only
        state.history = [m for m in state.history if m.role == "system"]
        state.total_tokens_used = 0
        state.tokens_estimated = False

        # Wipe all bubble widgets from the conversation view
        for child in list(conv.children):
            await child.remove()

        # Reset internal tracking
        self._bubble_pairs.clear()
        self._undo_checkpoints.clear()
        self._turn_bubbles.clear()

        # Restore startup logo and show confirmation
        tagline = f"Think anything. Ask anything.  •  v{__version__}"
        conv.add_bubble(LogoBubble(_BANNER, tagline, t))
        conv.add_bubble(
            SystemBubble(
                "✓ Conversation cleared. Previous messages saved to session history.",
                t,
                kind="success",
            )
        )
        self.query_one(HUDWidget).update_from_state(self._ctx, state)

    async def _handle_exec_confirmation(self, text: str) -> None:
        """Execute code if confirmed, or cancel."""
        data = self._pending_exec_data
        self._pending_exec_data = None
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        if text.lower() in ("y", "yes") and data is not None:
            self.run_worker(
                self._run_exec_tool(data.get("language", "python"), data.get("code", "")),
                exclusive=False,
                exit_on_error=False,
            )
        else:
            conv.add_bubble(SystemBubble("Execution cancelled.", t, kind="info"))

    async def _handle_browse_confirmation(self, text: str) -> None:
        """Fetch web content if confirmed, or cancel."""
        data = self._pending_browse_data
        self._pending_browse_data = None
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        if text.lower() in ("y", "yes") and data is not None:
            self.run_worker(
                self._run_browse_tool(data.get("url", ""), data.get("query", "")),
                exclusive=False,
                exit_on_error=False,
            )
        else:
            conv.add_bubble(SystemBubble("Browse cancelled.", t, kind="info"))

    async def _handle_mcp_confirmation(self, text: str) -> None:
        """Execute MCP tool call if confirmed, or cancel."""
        data = self._pending_mcp_data
        self._pending_mcp_data = None
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        if text.lower() in ("y", "yes") and data is not None:
            tool_name = data.get("tool", "")
            arguments = {k: v for k, v in data.items() if k != "tool"}
            self.run_worker(
                self._run_mcp_tool(tool_name, arguments),
                exclusive=False,
                exit_on_error=False,
            )
        else:
            conv.add_bubble(SystemBubble("MCP call cancelled.", t, kind="info"))

    async def _start_voice_recording(self) -> None:
        """Start non-blocking microphone capture."""
        from anythink.voice.recorder import VoiceRecorder

        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        try:
            recorder = VoiceRecorder()
            recorder.start()
        except VoiceError as exc:
            conv.add_bubble(SystemBubble(exc.user_message, t, kind="error"))
            return
        except Exception as exc:
            conv.add_bubble(SystemBubble(f"Voice error: {exc}", t, kind="error"))
            return

        self._voice_recorder = recorder
        self._pending_voice = True
        conv.add_bubble(
            SystemBubble(
                f"🎙 Recording… (model: {self._ctx.config.voice_model})\n"
                "Press Enter to stop and transcribe.",
                t,
                kind="info",
            )
        )

    async def _finish_voice_recording(self) -> None:
        """Worker: stop recorder, transcribe, inject text into input."""
        import asyncio

        from anythink.voice.transcriber import VoiceTranscriber

        t = self._ctx.theme
        conv = self.query_one(ConversationView)
        recorder: Any = self._voice_recorder
        self._voice_recorder = None

        if recorder is None:
            return

        try:
            audio = await asyncio.to_thread(recorder.stop)
        except VoiceError as exc:
            conv.add_bubble(SystemBubble(exc.user_message, t, kind="error"))
            return
        except Exception as exc:
            conv.add_bubble(SystemBubble(f"Recording failed: {exc}", t, kind="error"))
            return

        conv.add_bubble(SystemBubble("Transcribing…", t, kind="info"))

        try:
            transcriber = VoiceTranscriber(
                model_name=self._ctx.config.voice_model,
                language=self._ctx.config.voice_language,
            )
            text = await asyncio.to_thread(transcriber.transcribe, audio)
        except VoiceError as exc:
            conv.add_bubble(SystemBubble(exc.user_message, t, kind="error"))
            return
        except Exception as exc:
            conv.add_bubble(SystemBubble(f"Transcription failed: {exc}", t, kind="error"))
            return

        if not text:
            conv.add_bubble(SystemBubble("No speech detected.", t, kind="warning"))
            return

        # Place transcribed text into the input widget (editable before sending)
        inp = self.query_one(Input)
        inp.value = f"🎙 {text}"
        inp.focus()
        conv.add_bubble(SystemBubble(f"Transcribed: {text!r}", t, kind="success"))

    async def _switch_branch(self, branch_name: str) -> None:
        """Switch to *branch_name* and redraw the conversation."""
        if self._state is None:
            return
        state = self._state
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        bm = BranchManager(state)
        if not bm.switch_to(branch_name):
            conv.add_bubble(SystemBubble(f"Branch '{branch_name}' not found.", t, kind="error"))
            return

        # Clear all existing bubbles
        for child in list(conv.children):
            await child.remove()

        # Reset tracking
        self._bubble_pairs.clear()
        self._undo_checkpoints.clear()
        self._turn_bubbles.clear()

        # Remount the branch's conversation history as finalized bubbles
        non_sys = [m for m in state.history if m.role != "system"]
        for i in range(0, len(non_sys), 2):
            user_msg = non_sys[i]
            u_text = user_msg.content if isinstance(user_msg.content, str) else "…"
            user_bub = UserBubble(u_text, t, config=self._ctx.config)
            await conv.mount(user_bub)

            if i + 1 < len(non_sys):
                ai_msg = non_sys[i + 1]
                a_text = ai_msg.content if isinstance(ai_msg.content, str) else "…"
                turn_idx = state.history.index(ai_msg)
                ai_bub = AIBubble(
                    t,
                    model_alias=state.model_id,
                    provider=state.provider.display_name,
                    config=self._ctx.config,
                )
                ai_bub.finalize(a_text)
                await conv.mount(ai_bub)
                self._bubble_pairs.append((user_bub, ai_bub))
                self._undo_checkpoints.append(i)
                self._turn_bubbles[turn_idx] = ai_bub

        conv.scroll_end(animate=False)
        icon = get_icon("branch", self._ctx.config)
        conv.add_bubble(SystemBubble(f"{icon} Switched to {branch_name!r}.", t, kind="info"))

        # Update HUD
        hud = self.query_one(HUDWidget)
        hud.branch = branch_name
        hud.update_from_state(self._ctx, state)

    # ── async workers ──────────────────────────────────────────────────────

    async def _dispatch_command(self, text: str) -> None:
        """Dispatch a slash command and show the result in a SystemBubble."""
        if self._state is None:
            return
        t = self._ctx.theme
        conv = self.query_one(ConversationView)
        result = await self._cmd_registry.dispatch(text, self._ctx, self._state)

        # Handle TUI-layer signals
        if result.action == "open_settings":
            import contextlib

            with contextlib.suppress(Exception):
                self.query_one(SettingsMenu).open()
            return

        if result.action == "clear_confirm":
            self._pending_clear = True
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="warning"))
            return

        if result.action == "undo_request":
            self._pending_undo = True
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="warning"))
            return

        if result.action == "branch_confirm":
            self._pending_branch_create = True
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="info"))
            return

        if result.action.startswith("branch_switch:"):
            branch_name = result.action.split(":", 1)[1]
            await self._switch_branch(branch_name)
            return

        if result.action == "branch_hud_update" and self._state is not None:
            hud = self.query_one(HUDWidget)
            hud.branch = self._state.active_branch
            hud.update_from_state(self._ctx, self._state)

        if result.action == "rag_hud_update" and self._state is not None:
            self.query_one(HUDWidget).update_from_state(self._ctx, self._state)

        if result.action == "search_hud_update" and self._state is not None:
            self.query_one(HUDWidget).update_from_state(self._ctx, self._state)

        if result.action == "rag_settings_open":
            try:
                rsm = self.query_one(RAGSettingsMenu)
                rsm.open()
            except Exception:
                if result.message:
                    conv.add_bubble(SystemBubble(result.message, t, kind="info"))
            return

        if result.action == "rag_index_wizard":
            prefill = result.extra.get("prefill_name", "") if result.extra else ""
            await self._start_rag_wizard(prefill_name=str(prefill))
            return

        if result.action == "rag_benchmark":
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="info"))
            return

        if result.action.startswith("rag_ingest_start:") and self._state is not None:
            # Format: rag_ingest_start:<name>:<mode>[:<extra_path>]
            parts = result.action.split(":", 3)
            index_name = parts[1] if len(parts) > 1 else ""
            ingest_mode = parts[2] if len(parts) > 2 else "incremental"
            extra_path = parts[3] if len(parts) > 3 else None
            if index_name:
                self.run_worker(
                    self._run_rag_ingest(index_name, ingest_mode, extra_path=extra_path),
                    exclusive=False,
                    exit_on_error=False,
                )
            return

        if result.action == "voice_request":
            await self._start_voice_recording()
            return

        if result.action == "exec_request" and self._state is not None:
            if self._ctx.config.exec_mode == "auto":
                self.run_worker(
                    self._run_exec_tool(
                        str(result.extra.get("language", "python")),
                        str(result.extra.get("code", "")),
                    ),
                    exclusive=False,
                    exit_on_error=False,
                )
            else:
                self._pending_exec_data = {k: str(v) for k, v in result.extra.items()}
                if result.message:
                    conv.add_bubble(SystemBubble(result.message, t, kind="code"))
            return

        if result.action == "browse_request" and self._state is not None:
            if self._ctx.config.browse_autonomy == "auto":
                self.run_worker(
                    self._run_browse_tool(
                        str(result.extra.get("url", "")),
                        str(result.extra.get("query", "")),
                    ),
                    exclusive=False,
                    exit_on_error=False,
                )
            else:
                self._pending_browse_data = {k: str(v) for k, v in result.extra.items()}
                if result.message:
                    conv.add_bubble(SystemBubble(result.message, t, kind="search"))
            return

        if result.action == "mcp_call_request" and self._state is not None:
            if self._ctx.config.exec_mode == "auto":
                self.run_worker(
                    self._run_mcp_tool(
                        str(result.extra.get("tool", "")),
                        {k: v for k, v in result.extra.items() if k != "tool"},
                    ),
                    exclusive=False,
                    exit_on_error=False,
                )
            else:
                self._pending_mcp_data = {k: str(v) for k, v in result.extra.items()}
                if result.message:
                    conv.add_bubble(SystemBubble(result.message, t, kind="code"))
            return

        if result.action.startswith("rag_rebuild:") and self._state is not None:
            index_name = result.action.split(":", 1)[1]
            self.run_worker(
                self._rebuild_rag_index(index_name),
                exclusive=False,
                exit_on_error=False,
            )

        if result.action == "compare_request":
            aliases = result.extra.get("aliases", [])
            if aliases:
                self._pending_compare_aliases = list(aliases)
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="info"))
            return

        if result.action == "template_send":
            rendered = result.extra.get("rendered", "")
            if rendered and self._state is not None:
                inp = self.query_one(Input)
                inp.value = rendered
                inp.focus()
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="info"))
            return

        if result.action == "update_confirm":
            self._pending_update = True
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="warning"))
            return

        if result.action == "schedule_run":
            schedule_name = result.extra.get("schedule_name", "")
            if schedule_name:
                self.run_worker(
                    self._run_schedule(schedule_name),
                    exclusive=False,
                    exit_on_error=False,
                )
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="info"))
            return

        if result.action == "model_switched":
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="success"))
            if self._state is not None:
                hud = self.query_one(HUDWidget)
                hud.update_from_state(self._ctx, self._state)
            return

        if result.action == "debug_hud_update":
            dm = self._ctx.debug_manager
            hud = self.query_one(HUDWidget)
            hud.debug_active = dm.is_active()
            hud.debug_level = dm.level()
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="info"))
            return

        if result.action == "debug_panel_toggle":
            self._toggle_debug_panel()
            dm = self._ctx.debug_manager
            label = "open" if dm.panel_open() else "closed"
            conv.add_bubble(SystemBubble(f"Debug panel {label}", t, kind="info"))
            return

        if result.action == "debug_display":
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="info"))
            return

        if result.action == "replay_stream" and self._state is not None:
            record_id = result.extra.get("record_id")
            provider_alias = result.extra.get("provider_alias")
            dm = self._ctx.debug_manager
            rec = dm.get(record_id) if record_id else dm.latest()
            if rec is not None:
                if result.message:
                    conv.add_bubble(SystemBubble(result.message, t, kind="info"))
                self.run_worker(
                    self._stream_replay(rec, provider_alias),
                    exclusive=False,
                    exit_on_error=False,
                )
            else:
                conv.add_bubble(SystemBubble("No record found to replay.", t, kind="error"))
            return

        # ── V4 MMOS action signals ─────────────────────────────────────────
        if result.action == "open_optimize_panel":
            import contextlib

            with contextlib.suppress(Exception):
                self.query_one(OptimizePanel).open()
            return

        if result.action == "open_ratelimit_panel":
            import contextlib

            with contextlib.suppress(Exception):
                self.query_one(RateLimitPanel).open(self._ctx, self._ctx.theme)
            return

        if result.action == "mmos_hud_update":
            self._sync_mmos_hud()
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="info"))
            return

        if result.action == "optimize_reset_confirm":
            self._pending_optimize_reset = True
            if result.message:
                conv.add_bubble(SystemBubble(result.message, t, kind="warning"))
            return

        if result.action == "open_optimize_registry":
            caps = self._ctx.mmos_registry.all()
            lines = [f"Model Capability Registry  ({len(caps)} entries)", ""]
            for cap in caps[:20]:
                strengths = ", ".join(cap.strength_categories[:3]) or "general"
                lines.append(f"  {cap.id:<42} {cap.tier:<10} {cap.speed_class:<7} {strengths}")
            if len(caps) > 20:
                lines.append(f"  … and {len(caps) - 20} more")
            conv.add_bubble(SystemBubble("\n".join(lines), t, kind="info"))
            return

        if result.action in ("open_optimize_registry_add", "open_optimize_registry_edit"):
            model_id = result.extra.get("model_id", "")
            action_label = "add" if result.action.endswith("_add") else f"edit: {model_id}"
            conv.add_bubble(
                SystemBubble(
                    f"Registry {action_label} — use /optimize registry commands to manage entries.",
                    t,
                    kind="info",
                )
            )
            return

        if result.should_exit:
            self.exit(0)
            return

        if result.message:
            kind = "error" if result.error else "info"
            conv.add_bubble(SystemBubble(result.message, t, kind=kind))

        # Refresh HUD after state-mutating commands (/rename, /search, etc.)
        if self._state is not None:
            hud = self.query_one(HUDWidget)
            hud.branch = self._state.active_branch
            hud.update_from_state(self._ctx, self._state)

        # Update bookmark indicators for any newly bookmarked turns
        self._sync_bookmark_indicators()

    def _error_suggestion(self, exc: AnythinkError) -> str | None:
        """Map a known exception type to a suggested fix command."""
        from anythink.exceptions import (
            AuthenticationError,
            ModelNotFoundError,
            ProviderUnavailableError,
            RAGError,
            RateLimitError,
            ToolExecutionError,
        )

        if isinstance(exc, AuthenticationError):
            provider = getattr(exc, "provider", "")
            if provider:
                return f"Run /keys update {provider} to enter a new key"
            return "Run /keys update <provider> to enter a new key"
        if isinstance(exc, RateLimitError):
            return "Try /model to switch to a different model alias"
        if isinstance(exc, ProviderUnavailableError):
            return "Check your connection; retry or run /keys test <provider>"
        if isinstance(exc, ModelNotFoundError):
            return "Run /model list to see available aliases"
        if isinstance(exc, RAGError):
            return "Run /rag rebuild <name> or /rag info <name>"
        if isinstance(exc, ToolExecutionError):
            return "Check the runtime is in PATH, or change via /settings"
        return None

    def _sync_bookmark_indicators(self) -> None:
        """Refresh ✦ in AIBubble titles to match current bookmark state."""
        if self._state is None:
            return
        bm_mgr = BookmarkManager(self._state.bookmarks)
        for turn_idx, bub in self._turn_bubbles.items():
            if bm_mgr.is_bookmarked(turn_idx) and not bub._is_bookmarked:
                bub.mark_bookmarked()
            elif not bm_mgr.is_bookmarked(turn_idx) and bub._is_bookmarked:
                bub.clear_bookmark()

    async def _stream_response(
        self,
        state: ChatState,
        bubble: AIBubble,
        query: str,
        *,
        thinking: ThinkingWidget | None = None,
        is_replay: bool = False,
        replay_request_id: int = 0,
        skip_rag: bool = False,
        inject_rag_results: list | None = None,
    ) -> None:
        """Stream the AI response token-by-token into *bubble*.

        Args:
            skip_rag:           When True, skip all RAG retrieval for this turn.
            inject_rag_results: When set, use these results directly as RAG
                                context (bypassing threshold check).  Used by
                                the no-match option [2] override flow.
        """
        import time

        buffer = ""
        t0 = time.monotonic()
        _got_usage = False
        _was_stopped = False
        dm = self._ctx.debug_manager

        self._active_ai_bubble = bubble
        self._stop_streaming = False
        import contextlib

        with contextlib.suppress(Exception):
            self.query_one(HintBar).set_streaming(True)

        # ── Debug: begin record ────────────────────────────────────────────
        _debug_record = None
        if dm.is_active():
            from anythink.session.models import _msg_to_dict

            trimmed_for_payload = _trim_history(state.history, state.context_window)
            try:
                payload = [_msg_to_dict(m) for m in trimmed_for_payload]
            except Exception:
                payload = []
            _debug_record = dm.begin_request(
                session_id=state.session_id,
                model_id=state.model_id,
                provider_name=state.provider.name,
                alias_name=state.model_id,
                prompt_payload=payload,
                gen_params=state.gen_params,
                t_start=t0,
            )
            _debug_record.rag_query = query

        # ── Debug panel: begin ─────────────────────────────────────────────
        _debug_panel = None
        if dm.is_active() and dm.panel_open():
            import contextlib as _cl

            with _cl.suppress(Exception):
                _debug_panel = self.query_one(DebugPanel)
                await _debug_panel.begin_request(
                    _debug_record.request_id if _debug_record else 0,
                    time.strftime("%H:%M:%S"),
                )

        try:
            # ── RAG retrieval ──────────────────────────────────────────────
            rag_mgr = self._ctx.rag_manager
            if rag_mgr.is_active and not skip_rag:
                if thinking is not None:
                    thinking.set_context("Retrieving context…")
                emb = self._ctx.embedding_registry.get_available(self._ctx.config.embedding_backend)
                if emb is not None or inject_rag_results is not None:
                    try:
                        _rag_threshold = self._ctx.config.rag_threshold

                        if inject_rag_results is not None:
                            # Phase 6: option [2] override — bypass threshold check
                            rag_results = list(inject_rag_results)
                        else:
                            if dm.is_active() and _debug_record is not None:
                                _debug_record.t_rag_start = time.monotonic()
                                _rag_top_k = self._ctx.config.rag_top_k + 7  # extra for inspector
                            else:
                                _rag_top_k = self._ctx.config.rag_top_k

                            def _rag_debug_cb(emb_ms: float, candidates: int) -> None:
                                if _debug_record is not None:
                                    _debug_record.rag_embedding_ms = emb_ms
                                    _debug_record.rag_candidates_evaluated = candidates

                            def _rag_stage_cb(stage: str) -> None:
                                if thinking is not None:
                                    thinking.set_context(stage)

                            async def _rag_expand_fn(short_query: str) -> str:
                                """Single-turn LLM call to expand a terse query."""
                                try:
                                    expanded_parts: list[str] = []
                                    expand_prompt = (
                                        f"Rephrase this search query more descriptively "
                                        f"in one sentence: {short_query}"
                                    )
                                    async for token in state.provider.stream_chat(
                                        messages=[
                                            {
                                                "role": "user",
                                                "content": expand_prompt,
                                            }
                                        ],
                                        model_id=state.model_id,
                                        api_key=state.api_key,
                                        max_tokens=60,
                                    ):
                                        expanded_parts.append(token)
                                    return "".join(expanded_parts).strip()
                                except Exception:
                                    return short_query

                            assert emb is not None  # guarded by outer check
                            rag_results = await rag_mgr.retrieve(
                                query,
                                emb,
                                top_k=_rag_top_k,
                                debug_callback=_rag_debug_cb if dm.is_active() else None,
                                stage_callback=_rag_stage_cb,
                                llm_expand_fn=_rag_expand_fn,
                            )
                            if dm.is_active() and _debug_record is not None:
                                _debug_record.t_rag_end = time.monotonic()
                                _debug_record.rag_results = list(rag_results)
                                if _debug_panel is not None:
                                    n = sum(
                                        1 for r in rag_results if r.relevance >= _rag_threshold
                                    )
                                    await _debug_panel.append_event(
                                        f"RAG retrieved {n} chunks above threshold",
                                        f"{_debug_record.rag_duration_ms():.0f}ms",
                                    )

                            # ── Phase 6: quality check + no-match flow ─────
                            if (
                                rag_results
                                and self._ctx.config.rag_quality_indicators
                                and self._ctx.config.rag_no_match_behavior != "passthrough"
                            ):
                                from anythink.rag.quality import compute_quality

                                _q_results = rag_results[: self._ctx.config.rag_top_k]
                                _quality = compute_quality(_q_results, _rag_threshold)

                                if not _quality.passed_threshold:
                                    # Remove thinking widget; bubble not yet in conv
                                    if thinking is not None:
                                        thinking.stop()
                                        import contextlib as _cl

                                        with _cl.suppress(Exception):
                                            await thinking.remove()
                                        thinking = None
                                    if self._bubble_pairs and self._bubble_pairs[-1][1] is bubble:
                                        self._bubble_pairs.pop()
                                    # Store state for 3-option menu
                                    self._pending_rag_nomatch = {
                                        "query": query,
                                        "results": rag_results,
                                        "quality": _quality,
                                    }
                                    _conv = self.query_one(ConversationView)
                                    top_pct = f"{_quality.top_score:.0%}"
                                    thr_pct = f"{_rag_threshold:.0%}"
                                    _active_name = rag_mgr.active_name or "index"
                                    _menu = (
                                        f"📚 No relevant context found in RAG index "
                                        f"'{_active_name}'.\n"
                                        f"Best match: {top_pct}  (threshold: {thr_pct})\n\n"
                                        f"Choose how to proceed:\n"
                                        f"  [1]  Answer from training data (ignore RAG)\n"
                                        f"  [2]  Show closest matches, decide to send anyway\n"
                                        f"  [3]  Rephrase your query"
                                    )
                                    _conv.add_bubble(
                                        SystemBubble(
                                            _menu, self._ctx.theme, kind="warning"
                                        )
                                    )
                                    self._active_ai_bubble = None
                                    import contextlib as _cl2

                                    with _cl2.suppress(Exception):
                                        self.query_one(HintBar).set_streaming(False)
                                    with _cl2.suppress(Exception):
                                        self.query_one(TipsBar).stop()
                                    return

                        # Inject top-k chunks that pass the relevance threshold
                        if inject_rag_results is not None:
                            # Override mode: inject all provided results
                            inject_results = list(inject_rag_results)[: self._ctx.config.rag_top_k]
                        else:
                            inject_results = [
                                r
                                for r in rag_results[: self._ctx.config.rag_top_k]
                                if r.relevance >= _rag_threshold
                            ]

                        if inject_results:
                            context_parts = "\n\n".join(
                                f"[Source: {r.source_label()}]\n{r.chunk_text}"
                                for r in inject_results
                            )
                            state.history[-1] = ChatMessage(
                                role="user",
                                content=[
                                    TextPart(f"[RAG Context]\n{context_parts}"),
                                    TextPart(query),
                                ],
                            )
                            # Phase 6: attach quality to bubble for footer rendering
                            if (
                                self._ctx.config.rag_quality_indicators
                                and inject_rag_results is None  # don't recompute for override
                            ):
                                from anythink.rag.quality import compute_quality as _cq

                                _inject_quality = _cq(inject_results, _rag_threshold)
                                bubble.set_rag_quality(_inject_quality, inject_results)
                            else:
                                bubble._retrieval_results = inject_results
                    except Exception:  # nosec B110 - RAG errors are non-fatal
                        if dm.is_active() and _debug_record is not None:
                            _debug_record.t_rag_end = time.monotonic()

            # ── Web search ─────────────────────────────────────────────────
            if state.search_enabled and self._ctx.config.search_cache_enabled:
                self._ctx.search_cache.evict_expired()

            if state.search_enabled:
                if thinking is not None:
                    thinking.set_context("Searching the web…")
                _conv = self.query_one(ConversationView)
                _search_progress = SystemBubble(
                    "Preparing search…", self._ctx.theme, kind="info", config=self._ctx.config
                )
                _conv.add_bubble(_search_progress)

                # 1. Rewrite query
                _raw_queries: list[str] = [query]
                if self._ctx.config.search_query_rewrite:
                    from anythink.search.rewriter import QueryRewriter as _QueryRewriter

                    _rewriter = _QueryRewriter(state.provider, state.model_id)
                    _raw_queries = await _rewriter.rewrite_multi(
                        query, _history_context(state)
                    )
                    _search_progress.set_message(f"Searching: {_raw_queries[0]!r}")

                # 2. Run orchestrator
                if dm.is_active() and _debug_record is not None:
                    _debug_record.t_search_start = time.monotonic()
                try:
                    _orch_result = await self._ctx.search_orchestrator.run(
                        _raw_queries,
                        date_from=_freshness_to_date(self._ctx.config.search_freshness),
                        safe_search=self._ctx.config.search_safe_search,
                        include_domains=list(self._ctx.config.search_include_domains),
                        exclude_domains=list(self._ctx.config.search_exclude_domains),
                        news_mode=(state.search_mode == "news"),
                        progress_cb=lambda msg: _search_progress.set_message(msg),
                    )
                    if dm.is_active() and _debug_record is not None:
                        _debug_record.t_search_end = time.monotonic()
                        if _debug_panel is not None:
                            await _debug_panel.append_event(
                                "Web search complete",
                                f"{_debug_record.search_duration_ms():.0f}ms",
                            )

                    # 3. Inject into history + update bubble
                    if _orch_result.results:
                        _inject_search_context(state, _orch_result.results, query)
                        _search_progress.set_message(
                            f"Found {len(_orch_result.results)} results"
                            f" · {_orch_result.elapsed_s:.1f}s"
                        )
                    else:
                        _search_progress.set_message("No search results found.")
                except SearchError as _se:
                    if dm.is_active() and _debug_record is not None:
                        _debug_record.t_search_end = time.monotonic()
                    _search_progress.set_message(f"Search failed: {_se.user_message}")

            # ── Debug: prompt assembled ────────────────────────────────────
            if dm.is_active() and _debug_record is not None:
                _debug_record.t_prompt_assembled = time.monotonic()

            # Replace ThinkingWidget with the real AIBubble before first token
            if thinking is not None:
                thinking.stop()
                await thinking.remove()
            conv = self.query_one(ConversationView)
            conv.add_bubble(bubble)

            if thinking is not None:
                thinking = None  # prevent double-remove in error path

            if dm.is_active() and _debug_record is not None:
                _debug_record.t_api_sent = time.monotonic()
                if _debug_panel is not None:
                    await _debug_panel.append_event("API call sent", "")

            chunk_stream = state.provider.stream_chat(
                messages=_trim_history(state.history, state.context_window),
                model=state.model_id,
                gen_params=state.gen_params,
            )
            _last_usage = None
            _first_token_seen = False
            _last_token_time = time.monotonic()
            _token_index = 0
            async for chunk in chunk_stream:
                if self._stop_streaming:
                    _was_stopped = True
                    if _debug_record is not None:
                        _debug_record.was_stopped_by_user = True
                    break
                _now = time.monotonic()
                if chunk.text:
                    if not _first_token_seen:
                        _first_token_seen = True
                        if dm.is_active() and _debug_record is not None:
                            _debug_record.t_first_token = _now
                            if _debug_panel is not None:
                                ttft = _debug_record.ttft_ms()
                                await _debug_panel.append_event(
                                    "First token received",
                                    f"TTFT {ttft:.0f}ms" if ttft is not None else "",
                                )
                    if dm.is_active() and _debug_record is not None and dm.level() >= 3:
                        delta_ms = (_now - _last_token_time) * 1000
                        from anythink.debug.models import TokenEntry

                        _debug_record.token_trace.append(
                            TokenEntry(_token_index, chunk.text, delta_ms)
                        )
                        _token_index += 1
                    _last_token_time = _now
                    buffer += chunk.text
                    bubble.append_text(chunk.text)
                if chunk.finish_reason and dm.is_active() and _debug_record is not None:
                    _debug_record.stop_reason = chunk.finish_reason
                if chunk.thinking_text and dm.is_active() and _debug_record is not None:
                    _debug_record.agent_thinking += chunk.thinking_text
                if chunk.usage:
                    # Accumulate across turns — do not overwrite
                    state.total_tokens_used += chunk.usage.total_tokens
                    state.tokens_estimated = False
                    _got_usage = True
                    _last_usage = chunk.usage
                    if dm.is_active() and _debug_record is not None:
                        _debug_record.usage = chunk.usage
                        _debug_record.completion_tokens = chunk.usage.completion_tokens

            # ── Debug: stream complete ─────────────────────────────────────
            if dm.is_active() and _debug_record is not None:
                _debug_record.t_stream_end = time.monotonic()
                if _debug_record.completion_tokens == 0 and buffer:
                    _debug_record.completion_tokens = len(buffer) // 4
                stream_s = _debug_record.stream_duration_ms() / 1000
                if stream_s > 0 and _debug_record.completion_tokens > 0:
                    _debug_record.tokens_per_second = _debug_record.completion_tokens / stream_s
                if _debug_panel is not None:
                    await _debug_panel.append_event(
                        "Stream complete",
                        f"{_debug_record.stream_duration_ms():.0f}ms",
                    )

            # Record spend after stream completes
            if _last_usage is not None and self._ctx.config.spend_tracking:
                from anythink.spend.pricing import estimate_cost

                cost = estimate_cost(state.provider.name, state.model_id, _last_usage)
                self._ctx.spend_tracker.record(
                    session_id=state.session_id,
                    model_id=state.model_id,
                    provider=state.provider.name,
                    usage=_last_usage,
                    cost_usd=cost,
                )

        except AnythinkError as exc:
            if thinking is not None:
                thinking.stop()
                with contextlib.suppress(Exception):
                    await thinking.remove()
            if state.history and state.history[-1].role == "user":
                state.history.pop()
            if self._undo_checkpoints:
                self._undo_checkpoints.pop()
            if self._bubble_pairs and self._bubble_pairs[-1][1] is bubble:
                self._bubble_pairs.pop()
            # Ensure bubble is in the conversation before showing error
            conv = self.query_one(ConversationView)
            with contextlib.suppress(Exception):
                conv.add_bubble(bubble)
            bubble.show_error(exc.user_message)
            suggestion = self._error_suggestion(exc)
            if suggestion:
                conv.add_bubble(
                    SystemBubble(
                        exc.user_message, self._ctx.theme, kind="error", suggestion=suggestion
                    )
                )
            self._ctx.notifier.notify(
                "provider_failure",
                "Anythink — Provider Error",
                exc.user_message[:100],
            )
            self._active_ai_bubble = None
            with contextlib.suppress(Exception):
                self.query_one(HintBar).set_streaming(False)
            with contextlib.suppress(Exception):
                self.query_one(TipsBar).stop()
            return

        # Fallback: estimate token count when provider did not return usage data
        if not _got_usage and buffer:
            estimated = len(buffer) // 4
            state.total_tokens_used += estimated
            state.tokens_estimated = True

        duration = time.monotonic() - t0

        # Finalize bubble: append "stopped" marker if generation was interrupted
        if _was_stopped:
            bubble.finalize(buffer + "\n\n⏹ Stopped by user")
        else:
            bubble.finalize(buffer)

        self._last_response_text = buffer
        self._active_ai_bubble = None
        self._stop_streaming = False
        with contextlib.suppress(Exception):
            self.query_one(HintBar).set_streaming(False)
        with contextlib.suppress(Exception):
            self.query_one(TipsBar).stop()

        turn_index = len(state.history)  # index of the AI message about to be appended
        state.history.append(ChatMessage(role="assistant", content=buffer))
        self._turn_bubbles[turn_index] = bubble

        if self._ctx.config.session_autosave and state.history:
            self._ctx.session_manager.save(_build_session(state))

        hud = self.query_one(HUDWidget)
        hud.update_from_state(self._ctx, state)
        if self._ctx.config.spend_tracking:
            hud.session_cost = self._ctx.spend_tracker.session_total(state.session_id)
        self._refresh_dashboard_panels()
        self._prune_history_tracking()

        # Slow-response notification
        if duration >= SLOW_RESPONSE_S:
            self._ctx.notifier.notify(
                "slow_response",
                "Anythink — Response Ready",
                f"Response took {duration:.0f}s.",
            )

        # Apply bookmark indicator if this turn was already bookmarked
        if BookmarkManager(state.bookmarks).is_bookmarked(turn_index):
            bubble.mark_bookmarked()

        # ── Debug: finalize record + set bubble footer ─────────────────────
        if dm.is_active() and _debug_record is not None:
            import time as _time

            _debug_record.t_render_end = _time.monotonic()
            dm.finalize_request(_debug_record)

            if _debug_panel is not None:
                await _debug_panel.finalize_request(_debug_record, dm.level())

            # Compose compact footer line on the AI bubble
            _footer_parts: list[str] = []
            if _debug_record.tokens_per_second:
                _footer_parts.append(f"{_debug_record.tokens_per_second:.0f} tok/s")
            if _debug_record.stop_reason:
                _footer_parts.append(f"stop: {_debug_record.stop_reason}")
            ttft_v = _debug_record.ttft_ms()
            if ttft_v is not None:
                _footer_parts.append(f"TTFT {ttft_v:.0f}ms")
            tw = _debug_record.total_wall_ms()
            if tw:
                _footer_parts.append(f"Total {tw:.0f}ms")
            if _footer_parts:
                _timer = get_icon("timer", self._ctx.config)
                bubble.set_debug_footer(f"  {_timer} " + " · ".join(_footer_parts))

    async def _run_rag_ingest(
        self,
        index_name: str,
        mode: str = "incremental",
        *,
        extra_path: str | None = None,
    ) -> None:
        """Background worker: run the 6-stage ingestion pipeline with live progress."""
        from anythink.rag.ingestion import IngestionProgress, run_ingestion

        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        emb = self._ctx.embedding_registry.get_available(self._ctx.config.embedding_backend)
        if emb is None:
            conv.add_bubble(
                SystemBubble(
                    "No embedding backend available. Install anythink[rag].",
                    t,
                    kind="error",
                )
            )
            return

        progress_bubble = SystemBubble(
            f"Starting {mode} ingestion of '{index_name}'…",
            t,
            kind="rag",
            config=self._ctx.config,
        )
        conv.add_bubble(progress_bubble)

        def _fmt_progress(prog: IngestionProgress) -> str:
            files_to_do = prog.files_new + prog.files_changed
            bar_width = 16
            if prog.chunks_total > 0:
                filled = int(bar_width * prog.chunks_embedded / max(1, prog.chunks_total))
                bar = "█" * filled + "░" * (bar_width - filled)
                pct = prog.chunks_embedded / max(1, prog.chunks_total) * 100
                chunk_line = (
                    f"\n  Chunks: {prog.chunks_embedded}/{prog.chunks_total}"
                    f"  |{bar}| {pct:.0f}%"
                )
            else:
                chunk_line = ""
            elapsed = (
                f"{prog.elapsed_s:.0f}s" if prog.elapsed_s < 60 else f"{prog.elapsed_s / 60:.1f}m"
            )
            eta = f"  ETA: {prog.eta_s:.0f}s" if prog.eta_s is not None else ""
            file_note = f"  ({prog.current_file})" if prog.current_file else ""
            return (
                f"⚙ Ingesting '{index_name}'  [{mode}]\n"
                f"  Stage {prog.stage}/6: {prog.stage_name}{file_note}\n"
                f"  Files: {prog.files_total}"
                f"  ({prog.files_new} new, {prog.files_changed} changed,"
                f" {prog.files_unchanged} unchanged)\n"
                f"  Parsed: {prog.files_parsed}/{files_to_do or prog.files_parsed}"
                f"  Failed: {prog.files_failed}"
                f"{chunk_line}\n"
                f"  Elapsed: {elapsed}{eta}"
            )

        def _on_progress(prog: IngestionProgress) -> None:
            progress_bubble.set_message(_fmt_progress(prog))

        try:
            result = await run_ingestion(
                index_name,
                self._ctx.rag_manager,
                emb,
                mode=mode,  # type: ignore[arg-type]
                extra_path=extra_path,
                progress_callback=_on_progress,
            )
        except RAGError as exc:
            progress_bubble.set_message(f"Ingestion failed: {exc.user_message}")
            return
        except Exception as exc:
            progress_bubble.set_message(f"Ingestion error: {exc}")
            return

        summary = (
            f"📚 '{index_name}' ingested: "
            f"{result.chunks_created:,} chunks from {result.files_processed} files"
            f" in {result.duration_s:.1f}s."
        )
        if result.errors:
            summary += f"\n  ⚠ {len(result.errors)} file(s) had errors and were skipped."
        progress_bubble.set_message(summary)

        if self._state is not None:
            self.query_one(HUDWidget).update_from_state(self._ctx, self._state)
        self._ctx.notifier.notify(
            "rag_build_done",
            "Anythink — RAG Ingestion Complete",
            f"'{index_name}': {result.chunks_created:,} chunks.",
        )

    async def _rebuild_rag_index(self, index_name: str) -> None:
        """Background worker: full rebuild — delegates to the ingestion pipeline."""
        await self._run_rag_ingest(index_name, mode="full")

    # ── RAG Phase 6: no-match 3-option flow ───────────────────────────────

    async def _handle_rag_nomatch(self, text: str) -> None:
        """Handle [1]/[2]/[3] choice after a RAG no-match event."""
        choice = text.strip()
        pending = self._pending_rag_nomatch
        if pending is None:
            return

        conv = self.query_one(ConversationView)
        t = self._ctx.theme
        query: str = pending["query"]
        results: list = pending["results"]

        if choice == "1":
            # Answer from training data — resend query without RAG
            self._pending_rag_nomatch = None
            await self._launch_retry_stream(query, skip_rag=True)

        elif choice == "2":
            # Show closest matches; transition to override-confirm state
            self._pending_rag_nomatch = None
            lines = ["Closest matches (below threshold):"]
            for i, r in enumerate(results[: self._ctx.config.rag_top_k + 2], 1):
                lines.append(f"  {i}. {r.source_label()}  [{r.relevance:.0%}]")
                lines.append(f"     {r.excerpt(80)}")
            lines.append("\nSend with this low-quality context anyway? [y/n]")
            conv.add_bubble(SystemBubble("\n".join(lines), t, kind="info"))
            self._pending_rag_override_confirm = {"query": query, "results": results}

        elif choice == "3":
            # Rephrase — pop the user message and pre-fill input
            self._pending_rag_nomatch = None
            if self._state and self._state.history and self._state.history[-1].role == "user":
                self._state.history.pop()
            inp = self.query_one(Input)
            inp.value = query
            inp.focus()
            conv.add_bubble(
                SystemBubble("Edit your query above and press Enter to retry.", t, kind="info")
            )

        else:
            conv.add_bubble(
                SystemBubble("Please enter 1, 2, or 3.", t, kind="info")
            )

    async def _handle_rag_override_confirm(self, text: str) -> None:
        """Handle y/n after the user sees the low-relevance chunk inspector."""
        choice = text.strip().lower()
        pending = self._pending_rag_override_confirm
        if pending is None:
            return

        conv = self.query_one(ConversationView)
        t = self._ctx.theme

        if choice in ("y", "yes"):
            self._pending_rag_override_confirm = None
            query: str = pending["query"]
            results: list = pending["results"]
            await self._launch_retry_stream(query, inject_rag_results=results)
        elif choice in ("n", "no"):
            self._pending_rag_override_confirm = None
            if self._state and self._state.history and self._state.history[-1].role == "user":
                self._state.history.pop()
            conv.add_bubble(
                SystemBubble(
                    "Cancelled. Rephrase your query and try again.", t, kind="info"
                )
            )
        else:
            conv.add_bubble(SystemBubble("Please enter y or n.", t, kind="info"))

    # ── RAG Phase 7: new-index wizard ─────────────────────────────────────

    async def _start_rag_wizard(self, prefill_name: str = "") -> None:
        """Launch the 8-step new-index creation wizard."""
        conv = self.query_one(ConversationView)
        t = self._ctx.theme

        if self._rag_wizard is None:
            self._rag_wizard = RAGIndexWizard(self._ctx)

        step = self._rag_wizard.start(prefill_name=prefill_name)
        conv.add_bubble(SystemBubble(step.prompt, t, kind="rag"))

    async def _handle_rag_wizard_step(self, text: str) -> None:
        """Process one wizard step and show the next prompt or completion."""
        if self._rag_wizard is None:
            return

        conv = self.query_one(ConversationView)
        t = self._ctx.theme

        step = self._rag_wizard.handle_input(text)
        conv.add_bubble(SystemBubble(step.prompt, t, kind="rag" if not step.done else "success"))

        if step.done:
            self._rag_wizard = None
            if step.cancelled:
                return
            if step.result is not None:
                try:
                    self._ctx.rag_manager.create_index(step.result)
                    if step.ingest_now:
                        self.run_worker(
                            self._run_rag_ingest(step.result.name, "incremental"),
                            exclusive=False,
                            exit_on_error=False,
                        )
                    if self._state is not None:
                        self.query_one(HUDWidget).update_from_state(self._ctx, self._state)
                except Exception as exc:
                    conv.add_bubble(
                        SystemBubble(f"Failed to create index: {exc}", t, kind="error")
                    )

    async def _launch_retry_stream(
        self,
        query: str,
        *,
        skip_rag: bool = False,
        inject_rag_results: list | None = None,
    ) -> None:
        """Create a new ThinkingWidget+AIBubble and launch _stream_response().

        Used by the RAG no-match handlers to retry the query with modified
        RAG behaviour (skip entirely, or inject override results).
        """
        if self._state is None:
            return

        state = self._state
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        thinking = ThinkingWidget(t)
        conv.add_bubble(thinking)

        bubble = AIBubble(
            t,
            model_alias=state.model_id,
            provider=state.provider.display_name,
            config=self._ctx.config,
        )

        import contextlib

        with contextlib.suppress(Exception):
            self.query_one(TipsBar).start()

        self.run_worker(
            self._stream_response(
                state,
                bubble,
                query,
                thinking=thinking,
                skip_rag=skip_rag,
                inject_rag_results=inject_rag_results,
            ),
            exclusive=False,
            exit_on_error=False,
        )

    async def _run_exec_tool(self, language: str, code: str) -> None:
        """Background worker: execute code and feed result to the AI."""
        from anythink.tools.exec import CodeExecTool

        t = self._ctx.theme
        conv = self.query_one(ConversationView)
        state = self._state
        if state is None:
            return

        tool = CodeExecTool()
        try:
            result = await tool.run(language=language, code=code)
        except ToolExecutionError as exc:
            conv.add_bubble(SystemBubble(exc.user_message, t, kind="error"))
            return

        stdout_text = result.stdout.strip() or "(no output)"
        stderr_text = result.stderr.strip()
        _gear = get_icon("settings", self._ctx.config)
        header = f"{_gear}  {language} · exit {result.exit_code} · {result.duration_s:.3f}s"
        body_parts = [header, f"stdout:\n{stdout_text}"]
        if stderr_text:
            body_parts.append(f"stderr:\n{stderr_text}")

        kind = "code" if result.succeeded else "error"
        conv.add_bubble(SystemBubble("\n".join(body_parts), t, kind=kind))
        self._log_tool_event(language, "exec", stdout_text[:120])
        self._log_tool_debug(
            name=f"exec:{language}",
            args={"language": language, "code": code[:120]},
            result_summary=stdout_text[:120],
            duration_s=result.duration_s,
            success=result.succeeded,
        )
        if result.duration_s >= SLOW_EXEC_S:
            self._ctx.notifier.notify(
                "exec_done",
                "Anythink — Code Executed",
                f"{language} finished in {result.duration_s:.1f}s.",
            )

        # Build context message for the AI
        result_ctx = (
            f"[Code Execution: {language}, exit {result.exit_code}, {result.duration_s:.3f}s]\n"
            f"stdout:\n{stdout_text}"
        )
        if stderr_text:
            result_ctx += f"\nstderr:\n{stderr_text}"

        self._undo_checkpoints.append(len(state.history))
        state.history.append(ChatMessage(role="user", content=result_ctx))

        ai_bubble = AIBubble(
            t,
            model_alias=state.model_id,
            provider=state.provider.display_name,
            config=self._ctx.config,
        )
        conv.add_bubble(ai_bubble)
        self._bubble_pairs.append((ai_bubble, ai_bubble))  # placeholder for undo tracking

        self.run_worker(
            self._stream_response(state, ai_bubble, result_ctx),
            exclusive=False,
            exit_on_error=False,
        )

    async def _run_browse_tool(self, url: str, query: str) -> None:
        """Background worker: fetch web content and feed it to the AI."""
        from anythink.browse.fetch import BrowseFetcher, BrowseTool

        t = self._ctx.theme
        conv = self.query_one(ConversationView)
        state = self._state
        if state is None:
            return

        target = url or query
        conv.add_bubble(SystemBubble(f"Browsing: {target}…", t, kind="search"))

        fetcher = BrowseFetcher(
            search_registry=self._ctx.search_registry,
            mode=self._ctx.config.browse_mode,
            preferred_search=self._ctx.config.search_provider,
        )
        tool = BrowseTool(fetcher)
        result = await tool.run(url=url, query=query)

        if not result.succeeded:
            conv.add_bubble(SystemBubble(result.stderr or "Browse failed.", t, kind="error"))
            return

        preview = result.stdout[:500] + ("…" if len(result.stdout) > 500 else "")
        mode_label = "Page" if url else "Search"
        header = f"🔍  {mode_label}: {target} ({result.duration_s:.2f}s)"
        conv.add_bubble(SystemBubble(f"{header}\n{preview}", t, kind="search"))
        self._log_tool_event(target, "browse", result.stdout[:120])
        self._log_tool_debug(
            name="browse",
            args={"url": url, "query": query},
            result_summary=result.stdout[:120],
            duration_s=result.duration_s,
            success=result.succeeded,
        )
        self._ctx.notifier.notify(
            "browse_done",
            "Anythink — Browse Complete",
            f"Fetched {target} ({result.duration_s:.1f}s).",
        )

        # Build context for the AI
        mode_full = "Web Page" if url else "Web Search"
        result_ctx = f"[{mode_full}: {target}, {result.duration_s:.2f}s]\n{result.stdout}"

        self._undo_checkpoints.append(len(state.history))
        state.history.append(ChatMessage(role="user", content=result_ctx))

        ai_bubble = AIBubble(
            t,
            model_alias=state.model_id,
            provider=state.provider.display_name,
            config=self._ctx.config,
        )
        conv.add_bubble(ai_bubble)
        self._bubble_pairs.append((ai_bubble, ai_bubble))  # placeholder for undo tracking

        self.run_worker(
            self._stream_response(state, ai_bubble, result_ctx),
            exclusive=False,
            exit_on_error=False,
        )

    async def _run_mcp_tool(self, tool_name: str, arguments: dict[str, str]) -> None:
        """Background worker: call an MCP tool and feed the result to the AI."""
        t = self._ctx.theme
        conv = self.query_one(ConversationView)
        state = self._state
        if state is None:
            return

        if not tool_name:
            conv.add_bubble(SystemBubble("No tool name specified.", t, kind="error"))
            return

        conv.add_bubble(SystemBubble(f"Calling MCP tool '{tool_name}'…", t, kind="code"))

        result = await self._ctx.mcp_manager.call_tool(tool_name, dict(arguments))

        header = f"🔌  {tool_name} [{result.server_name}] ({result.duration_s:.3f}s)"
        preview = result.content[:2000] + ("…" if len(result.content) > 2000 else "")
        kind = "error" if result.is_error else "code"
        conv.add_bubble(SystemBubble(f"{header}\n{preview}", t, kind=kind))
        self._log_tool_event(tool_name, result.server_name or "mcp", result.content[:120])
        self._log_tool_debug(
            name=f"mcp:{tool_name}",
            args=dict(arguments),
            result_summary=result.content[:120],
            duration_s=result.duration_s,
            success=not result.is_error,
        )

        result_ctx = (
            f"[MCP Tool: {tool_name} on {result.server_name}, {result.duration_s:.3f}s"
            + (" — ERROR" if result.is_error else "")
            + f"]\n{result.content}"
        )
        self._undo_checkpoints.append(len(state.history))
        state.history.append(ChatMessage(role="user", content=result_ctx))

        ai_bub = AIBubble(
            t,
            model_alias=state.model_id,
            provider=state.provider.display_name,
            config=self._ctx.config,
        )
        conv.add_bubble(ai_bub)
        self._bubble_pairs.append((ai_bub, ai_bub))

        self.run_worker(
            self._stream_response(state, ai_bub, result_ctx),
            exclusive=False,
            exit_on_error=False,
        )

    # ── V3: Multi-model comparison ─────────────────────────────────────────

    async def _run_comparison(self, state: ChatState, prompt: str, aliases: list[str]) -> None:
        """Background worker: run the same prompt against multiple models in parallel."""
        from anythink.compare.runner import run_comparison
        from anythink.providers.base import ChatMessage as _CM

        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        # Build the message list (include existing history context)
        messages = _trim_history(state.history, state.context_window)
        messages = messages + [_CM(role="user", content=prompt)]

        results = await run_comparison(self._ctx, aliases, messages)

        # Display each result sequentially
        for i, r in enumerate(results, 1):
            header = f"[{i}] {r.alias}  ({r.provider_name} / {r.model_id})"
            if r.error:
                body = f"Error: {r.error}"
                conv.add_bubble(SystemBubble(f"{header}\n{body}", t, kind="error"))
            else:
                meta_parts = [f"{r.elapsed_s:.1f}s"]
                if r.usage:
                    meta_parts.append(f"{r.usage.prompt_tokens}+{r.usage.completion_tokens} tok")
                if r.cost_usd > 0:
                    meta_parts.append(f"~${r.cost_usd:.4f}")
                meta = "  •  ".join(meta_parts)
                body = r.text or "(empty response)"
                conv.add_bubble(SystemBubble(f"══ {header}  [{meta}] ══\n{body}", t, kind="info"))

                # Record spend
                if r.usage is not None and self._ctx.config.spend_tracking:
                    self._ctx.spend_tracker.record(
                        session_id=state.session_id,
                        model_id=r.model_id,
                        provider=r.provider_name,
                        usage=r.usage,
                        cost_usd=r.cost_usd,
                    )

        # Store results for the pick step
        self._pending_compare_results = results
        self._pending_compare_pick = True

        alias_picks = "  ".join(f"[{i}] {r.alias}" for i, r in enumerate(results, 1))
        conv.add_bubble(
            SystemBubble(
                f"Continue with which response?\n{alias_picks}  [N] Cancel",
                t,
                kind="warning",
            )
        )

    async def _handle_compare_pick(self, text: str) -> None:
        """Process the user's pick from a completed comparison."""
        self._pending_compare_pick = False
        results = self._pending_compare_results
        self._pending_compare_results = None

        t = self._ctx.theme
        conv = self.query_one(ConversationView)
        state = self._state

        if text.lower() in ("n", "no", "cancel", "") or results is None or state is None:
            conv.add_bubble(
                SystemBubble("Comparison closed. No response added to history.", t, kind="info")
            )
            return

        try:
            idx = int(text.strip()) - 1
        except ValueError:
            conv.add_bubble(
                SystemBubble(
                    f"Invalid pick '{text}'. Type 1-{len(results)} or N to cancel.",
                    t,
                    kind="error",
                )
            )
            self._pending_compare_results = results
            self._pending_compare_pick = True
            return

        if not (0 <= idx < len(results)):
            conv.add_bubble(
                SystemBubble(
                    f"Pick out of range. Enter 1-{len(results)} or N to cancel.",
                    t,
                    kind="error",
                )
            )
            self._pending_compare_results = results
            self._pending_compare_pick = True
            return

        winner = results[idx]
        if winner.error:
            conv.add_bubble(
                SystemBubble(
                    f"Cannot continue with '{winner.alias}' — it returned an error.",
                    t,
                    kind="error",
                )
            )
            return

        # Add the prompt as user message and winner's response as assistant message
        from anythink.providers.base import ChatMessage as _CM

        state.history.append(_CM(role="user", content=winner.text or ""))
        state.history.append(_CM(role="assistant", content=winner.text or ""))
        self._last_response_text = winner.text or ""

        if self._ctx.config.session_autosave:
            self._ctx.session_manager.save(_build_session(state))

        conv.add_bubble(
            SystemBubble(
                f"✓ Continuing with [{winner.alias}] response.",
                t,
                kind="success",
            )
        )
        self.query_one(HUDWidget).update_from_state(self._ctx, state)

    # ── V3: Update confirm handler ─────────────────────────────────────────

    async def _handle_update_confirmation(self, text: str) -> None:
        """Run upgrade if the user confirms."""
        self._pending_update = False
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        if text.lower() not in ("y", "yes"):
            conv.add_bubble(SystemBubble("Upgrade cancelled.", t, kind="info"))
            return

        conv.add_bubble(SystemBubble("Upgrading Anythink…", t, kind="info"))
        import asyncio

        from anythink.updater import run_upgrade

        ok, output = await asyncio.to_thread(run_upgrade)
        if ok:
            conv.add_bubble(
                SystemBubble(
                    "✓ Upgrade complete. Restart Anythink to use the new version.",
                    t,
                    kind="success",
                )
            )
        else:
            short_output = output[-300:] if len(output) > 300 else output
            conv.add_bubble(SystemBubble(f"Upgrade failed:\n{short_output}", t, kind="error"))

    # ── V3: Schedule run-now worker ────────────────────────────────────────

    async def _run_schedule(self, schedule_name: str) -> None:
        """Background worker: run a named schedule immediately."""
        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        schedule = self._ctx.schedule_manager.get(schedule_name)
        if schedule is None:
            conv.add_bubble(SystemBubble(f"Schedule '{schedule_name}' not found.", t, kind="error"))
            return

        conv.add_bubble(SystemBubble(f"Running schedule '{schedule_name}'…", t, kind="info"))

        try:
            alias_name = schedule.alias or self._ctx.config.default_model_alias
            if not alias_name:
                conv.add_bubble(
                    SystemBubble("No model alias configured for this schedule.", t, kind="error")
                )
                return

            alias = self._ctx.model_registry.get(alias_name)
            if alias is None:
                conv.add_bubble(
                    SystemBubble(f"Model alias '{alias_name}' not found.", t, kind="error")
                )
                return

            api_key = self._ctx.key_manager.get_key(alias.provider)
            prov_cls = self._ctx.provider_registry.get(alias.provider)
            if prov_cls is None:
                conv.add_bubble(
                    SystemBubble(f"Provider '{alias.provider}' not registered.", t, kind="error")
                )
                return

            provider = prov_cls(api_key=api_key)
            from anythink.providers.base import ChatMessage as _CM

            messages = [_CM(role="user", content=schedule.prompt)]
            full_text = ""
            async for chunk in provider.stream_chat(
                messages, alias.model_id, gen_params=alias.gen_params
            ):
                full_text += chunk.text

            # Write to output file if configured
            if schedule.output_file:
                from pathlib import Path

                out = Path(schedule.output_file)
                out.parent.mkdir(parents=True, exist_ok=True)
                with out.open("a", encoding="utf-8") as f:
                    from datetime import datetime

                    f.write(f"\n\n--- {datetime.utcnow().isoformat()} ---\n{full_text}\n")

            # Update last_run
            from datetime import datetime

            self._ctx.schedule_manager.update_last_run(schedule_name, datetime.utcnow())

            preview = full_text[:400] + ("…" if len(full_text) > 400 else "")
            conv.add_bubble(
                SystemBubble(
                    f"✓ Schedule '{schedule_name}' completed:\n{preview}", t, kind="success"
                )
            )
            self._ctx.notifier.notify(
                "schedule_done",
                f"Anythink — Schedule '{schedule_name}'",
                full_text[:100],
            )
        except Exception as exc:
            conv.add_bubble(
                SystemBubble(f"Schedule '{schedule_name}' failed: {exc}", t, kind="error")
            )

    # ── V4 MMOS helpers ────────────────────────────────────────────────────

    def _sync_mmos_hud(self) -> None:
        """Update HUD reactive fields from the live optimize settings."""
        import contextlib

        with contextlib.suppress(Exception):
            s = self._ctx.mmos_settings.get()
            hud = self.query_one(HUDWidget)
            hud.mmos_enabled = s.enabled
            hud.mmos_mode = s.mode
            hud.mmos_strategy = s.mixing_mode

    # ── V4 MMOS widget message handlers ───────────────────────────────────

    def on_micro_prompt_widget_confirmed(self, event: MicroPromptWidget.Confirmed) -> None:
        self._microprompt_result = event.intent
        self._microprompt_event.set()

    def on_micro_prompt_widget_skipped(self, _event: MicroPromptWidget.Skipped) -> None:
        self._microprompt_result = None
        self._microprompt_event.set()

    def on_plan_review_panel_approved(self, _event: PlanReviewPanel.Approved) -> None:
        self._plan_approval_result = True
        self._plan_approval_event.set()

    def on_plan_review_panel_rejected(self, _event: PlanReviewPanel.Rejected) -> None:
        self._plan_approval_result = False
        self._plan_approval_event.set()

    def on_plan_review_panel_regenerate(self, _event: PlanReviewPanel.Regenerate) -> None:
        self._plan_approval_result = False
        self._plan_approval_event.set()

    def on_phase_tracker_panel_abort_requested(
        self, _event: PhaseTrackerPanel.AbortRequested
    ) -> None:
        self._plan_abort_signal.set()

    def on_phase_tracker_panel_pause_requested(
        self, _event: PhaseTrackerPanel.PauseRequested
    ) -> None:
        import contextlib

        with contextlib.suppress(Exception):
            self.query_one(ConversationView).add_bubble(
                SystemBubble(
                    "Plan Mode paused. Press any key to resume…",
                    self._ctx.theme,
                    kind="info",
                )
            )

    def on_override_caution_modal_proceed(self, _event: OverrideCautionModal.Proceed) -> None:
        self._override_proceed = True
        self._override_confirm_event.set()

    def on_override_caution_modal_use_recommended(
        self, _event: OverrideCautionModal.UseRecommended
    ) -> None:
        self._override_proceed = False
        self._override_confirm_event.set()

    def on_override_caution_modal_cancelled(self, _event: OverrideCautionModal.Cancelled) -> None:
        self._override_proceed = False
        self._override_confirm_event.set()

    def on_optimize_panel_closed(self, _event: OptimizePanel.Closed) -> None:
        self._sync_mmos_hud()

    # ── V4 MMOS query worker ───────────────────────────────────────────────

    async def _run_mmos_query(self, state: ChatState, raw_text: str) -> None:
        """V4 MMOS query pipeline worker.

        Runs routing, context selection, and the chosen mixing strategy.
        Interactive steps (microprompt, plan approval) use asyncio.Event.
        """
        import asyncio
        import contextlib
        import dataclasses
        import time

        from anythink.optimize.classifier import IntentClassifier
        from anythink.optimize.models import QueryIntent, RoutingDecision, TurnMMOSMetadata
        from anythink.providers.base import BaseProvider
        from anythink.providers.base import ChatMessage as _CM

        t = self._ctx.theme
        conv = self.query_one(ConversationView)
        classifier = IntentClassifier()
        opt = self._ctx.mmos_settings.get()

        # 1. Extract override flags
        clean_query, override_flags = classifier.extract_override_flags(raw_text)
        effective_query = clean_query or raw_text

        # 2. Show AI bubble + thinking widget
        bubble = AIBubble(t, model_alias="MMOS", provider="", config=self._ctx.config)
        thinking = ThinkingWidget(t)

        def _add_bubble_pair() -> None:
            conv.add_bubble(bubble)
            conv.add_bubble(thinking)

        self.call_from_thread(_add_bubble_pair)

        # 3. Classify intent (system inference as baseline)
        intent: QueryIntent = classifier.classify(effective_query)

        # 4. Micro-prompt (if enabled — don't block >30s)
        if opt.microprompt_enabled:
            self._microprompt_event.clear()
            self._microprompt_result = None

            def _show_mp() -> None:
                with contextlib.suppress(Exception):
                    self.query_one(MicroPromptWidget).show(intent.category, t)

            self.call_from_thread(_show_mp)
            try:
                await asyncio.wait_for(self._microprompt_event.wait(), timeout=30.0)
                if self._microprompt_result is not None:
                    intent = self._microprompt_result
            except TimeoutError:
                pass

            def _hide_mp() -> None:
                with contextlib.suppress(Exception):
                    self.query_one(MicroPromptWidget).hide()

            self.call_from_thread(_hide_mp)

        # 5. Select relevant history
        thinking.set_context("Selecting context…")
        try:
            relevant_history = await self._ctx.context_engine.select_relevant_history(
                state.history, effective_query
            )
        except Exception:
            relevant_history = list(state.history)

        # Build messages list for model calls
        user_msg = _CM(role="user", content=effective_query)
        messages_for_model = relevant_history + [user_msg]

        # 6. Routing decision
        hist_tokens = sum(
            len(m.content if isinstance(m.content, str) else "") // 4 for m in relevant_history
        )
        try:
            routing_decision = self._ctx.routing_engine.decide(
                query=effective_query,
                intent=intent,
                history_token_estimate=hist_tokens,
                override_flags=override_flags,
                mode=opt.mode,
            )
        except Exception:
            routing_decision = RoutingDecision(strategy="routing", primary_model="")

        # 7. Override conflict check
        if override_flags.get("model"):
            token_estimate = classifier.estimate_tokens(effective_query)
            conflict = self._ctx.routing_engine.detect_override_conflict(
                override_flags, routing_decision, token_estimate
            )
            if conflict:
                self._override_confirm_event.clear()
                self._override_proceed = False

                def _show_caution() -> None:
                    with contextlib.suppress(Exception):
                        self.query_one(OverrideCautionModal).show_conflict(
                            override_flags.get("model", ""),
                            conflict,
                            routing_decision.primary_model,
                            t,
                        )

                self.call_from_thread(_show_caution)
                await self._override_confirm_event.wait()

                if not self._override_proceed:

                    def _cancel_bubbles() -> None:
                        with contextlib.suppress(Exception):
                            thinking.remove()
                        with contextlib.suppress(Exception):
                            bubble.show_error("Query cancelled.")

                    self.call_from_thread(_cancel_bubbles)
                    return

        # 8. Build provider resolver
        def _resolve_provider(model_id: str) -> tuple[BaseProvider, str] | None:
            if "/" not in model_id:
                return None
            provider_name, api_model_id = model_id.split("/", 1)
            try:
                api_key = self._ctx.key_manager.get_key(provider_name)
                base_url = self._ctx.config.local_servers.get(provider_name)
                provider = self._ctx.provider_registry.instantiate(provider_name, api_key, base_url)
                return provider, api_model_id
            except Exception:
                return None

        t0 = time.monotonic()

        # 9. Plan Mode
        if routing_decision.plan_mode and opt.plan_mode_enabled:
            thinking.set_context("Generating execution plan…")
            try:
                plan = await self._ctx.plan_engine.generate_plan(
                    query=effective_query,
                    intent=intent,
                    routing_decision=routing_decision,
                    provider_resolver=_resolve_provider,
                    session_id=state.session_id,
                    mode=opt.mode,
                )
            except Exception:
                plan = None

            if plan is not None and opt.plan_approval_required:
                self._pending_plan = plan
                self._plan_approval_event.clear()
                self._plan_approval_result = False

                def _show_review() -> None:
                    with contextlib.suppress(Exception):
                        self.query_one(PlanReviewPanel).show_plan(plan, t)

                self.call_from_thread(_show_review)
                await self._plan_approval_event.wait()

                if not self._plan_approval_result:

                    def _cancel_plan() -> None:
                        with contextlib.suppress(Exception):
                            thinking.remove()
                        with contextlib.suppress(Exception):
                            bubble.show_error("Plan rejected.")

                    self.call_from_thread(_cancel_plan)
                    return

            if plan is not None:
                self._plan_abort_signal.clear()

                from anythink.optimize.plan import PhaseUpdate

                def _show_tracker() -> None:
                    with contextlib.suppress(Exception):
                        tracker = self.query_one(PhaseTrackerPanel)
                        tracker.set_plan(plan, t)
                    with contextlib.suppress(Exception):
                        thinking.display = False

                self.call_from_thread(_show_tracker)

                def _on_phase_update(update: PhaseUpdate) -> None:
                    with contextlib.suppress(Exception):
                        self.call_from_thread(
                            self.query_one(PhaseTrackerPanel).update_phase, update
                        )

                try:
                    executed = await self._ctx.plan_runner.execute(
                        plan=plan,
                        provider_resolver=_resolve_provider,
                        on_phase_update=_on_phase_update,
                        abort_signal=self._plan_abort_signal,
                    )
                    final_text = executed.final_output or "[Plan completed — no output]"
                    model_ids = executed.unique_models
                    total_tokens = sum(len(p.output) // 4 for p in executed.phases)
                except Exception as exc:
                    final_text = f"[Plan execution error: {exc}]"
                    model_ids = []
                    total_tokens = 0

                def _hide_tracker() -> None:
                    with contextlib.suppress(Exception):
                        self.query_one(PhaseTrackerPanel).display = False

                self.call_from_thread(_hide_tracker)
            else:
                final_text = "[Plan generation failed]"
                model_ids = []
                total_tokens = 0

        else:
            # 10. Normal mixing strategy
            thinking.set_context("Thinking…")

            try:
                mix = await self._ctx.mixing_orchestrator.execute(
                    decision=routing_decision,
                    messages=messages_for_model,
                    intent=intent,
                    provider_resolver=_resolve_provider,
                    session_id=state.session_id,
                )
                final_text = mix.final_text
                model_ids = mix.metadata.model_ids
                total_tokens = mix.total_tokens
            except Exception as exc:
                final_text = f"[MMOS error: {exc}]"
                model_ids = []
                total_tokens = 0

        elapsed = time.monotonic() - t0

        # 11. Record MMOS metadata + append messages to history
        mmos_meta = TurnMMOSMetadata(
            strategy=routing_decision.strategy,
            model_ids=model_ids,
            intent=intent,
            routing_decision=routing_decision,
            total_tokens=total_tokens,
            elapsed_s=elapsed,
        )
        state.history.append(dataclasses.replace(user_msg, metadata={"mmos": mmos_meta.to_dict()}))
        ai_msg = _CM(role="assistant", content=final_text)
        state.history.append(ai_msg)
        state.total_tokens_used += total_tokens
        self._last_response_text = final_text

        # 12. Finalize bubble
        def _finish() -> None:
            with contextlib.suppress(Exception):
                thinking.remove()
            with contextlib.suppress(Exception):
                bubble.finalize_with_mmos(final_text, mmos_meta)

        self.call_from_thread(_finish)

        # 13. Update rate limits + HUD
        for mid in model_ids:
            self._ctx.rate_limit_manager.record_request(mid, max(1, total_tokens // len(model_ids)))

        self._sync_mmos_hud()

        # 14. Autosave
        if self._ctx.config.session_autosave:
            with contextlib.suppress(Exception):
                self._ctx.session_manager.save(_build_session(state))

        # 15. Notify on long responses
        if elapsed > 30.0:
            self._ctx.notifier.notify(
                "plan_mode_complete",
                "Anythink",
                f"MMOS response complete ({elapsed:.0f}s)",
            )

        # Prune tracking dicts
        self._prune_history_tracking()
