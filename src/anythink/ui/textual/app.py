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
    _format_search_results,
    _trim_history,
)
from anythink.bookmarks.manager import BookmarkManager
from anythink.branch.manager import BranchManager
from anythink.commands.registry import CommandRegistry
from anythink.exceptions import AnythinkError, SearchError, ToolExecutionError, VoiceError
from anythink.files.reader import ImageAttachment, TextAttachment
from anythink.notify.notifier import SLOW_EXEC_S, SLOW_RESPONSE_S
from anythink.providers.base import ChatMessage, ContentPart, TextPart
from anythink.session.manager import auto_session_name
from anythink.ui.banner import _BANNER
from anythink.ui.bubbles import AIBubble, LogoBubble, SystemBubble, UserBubble
from anythink.ui.hud import HUDWidget
from anythink.ui.startup import find_resumable_session, is_returning_user
from anythink.ui.textual.conversation import ConversationView
from anythink.ui.textual.hint_bar import HintBar
from anythink.ui.textual.input_area import InputArea
from anythink.ui.textual.panels.file_browser import FileBrowserTab
from anythink.ui.textual.panels.rag_browser import RAGBrowserTab
from anythink.ui.textual.panels.session_list import SessionListPanel
from anythink.ui.textual.panels.stats import StatsPanel
from anythink.ui.textual.panels.tool_output import ToolOutputTab
from anythink.ui.textual.settings_menu import SettingsMenu
from anythink.ui.textual.theme_bridge import resolve
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

    def __init__(self, ctx: AppContext, *, dashboard: bool = False) -> None:
        super().__init__()
        self._ctx = ctx
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

        # ── V3 state ───────────────────────────────────────────────────────
        # Compare mode: aliases set by /compare; cleared once comparison fires
        self._pending_compare_aliases: list[str] | None = None
        # Results from a completed comparison; cleared once user picks
        self._pending_compare_results: list[Any] | None = None
        self._pending_compare_pick: bool = False
        # Update confirm: set by /update when a newer version is available
        self._pending_update: bool = False

    # ── widget tree ────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield HUDWidget(self._ctx.theme, __version__, id="hud")
        with Horizontal(id="content-row"):
            yield SessionListPanel(self._ctx, id="left-panel")
            yield ConversationView()
            yield StatsPanel(self._ctx, id="right-panel")
        with TabbedContent(id="bottom-tabs"):
            with TabPane("Files", id="tab-files"):
                yield FileBrowserTab(id="file-browser")
            with TabPane("RAG", id="tab-rag"):
                yield RAGBrowserTab(self._ctx, id="rag-browser")
            with TabPane("Tools", id="tab-tools"):
                yield ToolOutputTab(id="tool-output")
        yield SettingsMenu(self._ctx, self._ctx.theme, id="settings-menu")
        yield TipsBar(self._ctx.theme, id="tips-bar")
        yield InputArea()
        yield HintBar(self._ctx.theme, id="hint-bar")

    def on_mount(self) -> None:
        """Resolve state, populate HUD, show startup/resume UI, and focus input."""
        t = self._ctx.theme
        ia = self.query_one(InputArea)
        ia.styles.border_top = ("solid", resolve(t.muted))
        ia.configure(list(self._cmd_registry.all_commands()), t)
        self.query_one(Input).focus()

        if self._dashboard_mode:
            self._apply_dashboard_layout(True)

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
                    )
                )
                return  # skip naming prompt while resume is pending

        # First-launch naming prompt
        self._naming_mode = True
        inp = self.query_one(Input)
        inp.placeholder = _INPUT_PLACEHOLDER_NAMING
        conv.add_bubble(
            SystemBubble(
                "Name this session?  (press Enter to auto-name)",
                t,
                kind="info",
            )
        )

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

        if not text or self._state is None:
            return

        t = self._ctx.theme
        conv = self.query_one(ConversationView)

        if text.startswith("/"):
            conv.add_bubble(UserBubble(text, t))
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
            conv.add_bubble(UserBubble(text, t))
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

        user_bub = UserBubble(text, t)
        conv.add_bubble(user_bub)

        # ThinkingWidget is a temporary placeholder; _stream_response replaces it
        thinking = ThinkingWidget(t)
        conv.add_bubble(thinking)

        bubble = AIBubble(t, model_alias=state.model_id, provider=state.provider.display_name)
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

    def action_escape_or_stop(self) -> None:
        """Escape: close settings if open; stop streaming if active; else focus input."""
        import contextlib

        # Settings overlay takes highest priority
        with contextlib.suppress(Exception):
            sm = self.query_one(SettingsMenu)
            if sm.is_open():
                sm.action_close()
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
        if self._state is None:
            return
        if event.field == "web_search_enabled":
            self._state.search_enabled = self._ctx.config.web_search_enabled
        if event.field == "active_theme":
            from anythink.ui.theme import get_theme

            new_theme = get_theme(self._ctx.config.active_theme)
            self._ctx.theme = new_theme
            self.query_one(HUDWidget)._theme = new_theme
        self.query_one(HUDWidget).update_from_state(self._ctx, self._state)

    def on_settings_menu_closed(self, event: SettingsMenu.Closed) -> None:
        """Return focus to the input after the settings overlay is dismissed."""
        self.query_one(Input).focus()
        if self._state is not None:
            # Final sync: ensure runtime state matches whatever was saved
            self._state.search_enabled = self._ctx.config.web_search_enabled
            self.query_one(HUDWidget).update_from_state(self._ctx, self._state)

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
            user_bub = UserBubble(u_text, t)
            await conv.mount(user_bub)
            if i + 1 < len(non_sys):
                ai_msg = non_sys[i + 1]
                a_text = ai_msg.content if isinstance(ai_msg.content, str) else "…"
                ai_bub = AIBubble(
                    t, model_alias=state.model_id, provider=state.provider.display_name
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

        name = text.strip() if text.strip() else auto_session_name(self._state.model_id)
        self._state.session_name = name
        self._naming_mode = False
        self.query_one(Input).placeholder = _INPUT_PLACEHOLDER_DEFAULT
        self.query_one(HUDWidget).update_from_state(self._ctx, self._state)
        conv.add_bubble(SystemBubble(f'Session named: "{name}"', t, kind="success"))

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
            user_bub = UserBubble(u_text, t)
            await conv.mount(user_bub)

            if i + 1 < len(non_sys):
                ai_msg = non_sys[i + 1]
                a_text = ai_msg.content if isinstance(ai_msg.content, str) else "…"
                turn_idx = state.history.index(ai_msg)
                ai_bub = AIBubble(
                    t,
                    model_alias=state.model_id,
                    provider=state.provider.display_name,
                )
                ai_bub.finalize(a_text)
                await conv.mount(ai_bub)
                self._bubble_pairs.append((user_bub, ai_bub))
                self._undo_checkpoints.append(i)
                self._turn_bubbles[turn_idx] = ai_bub

        conv.scroll_end(animate=False)
        conv.add_bubble(SystemBubble(f"🌿 Switched to {branch_name!r}.", t, kind="info"))

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
    ) -> None:
        """Stream the AI response token-by-token into *bubble*."""
        import time

        buffer = ""
        t0 = time.monotonic()
        _got_usage = False
        _was_stopped = False

        self._active_ai_bubble = bubble
        self._stop_streaming = False
        import contextlib

        with contextlib.suppress(Exception):
            self.query_one(HintBar).set_streaming(True)

        try:
            # ── RAG retrieval ──────────────────────────────────────────────
            rag_mgr = self._ctx.rag_manager
            if rag_mgr.is_active:
                if thinking is not None:
                    thinking.set_context("Retrieving context…")
                emb = self._ctx.embedding_registry.get_available(self._ctx.config.embedding_backend)
                if emb is not None:
                    try:
                        rag_results = await rag_mgr.retrieve(query, emb, top_k=5)
                        if rag_results:
                            context_parts = "\n\n".join(
                                f"[Source: {r.source_path}]\n{r.chunk_text}" for r in rag_results
                            )
                            state.history[-1] = ChatMessage(
                                role="user",
                                content=[
                                    TextPart(f"[RAG Context]\n{context_parts}"),
                                    TextPart(query),
                                ],
                            )
                            # Attach results to bubble for display after streaming
                            # (stored; applied in finalize path below)
                            bubble._retrieval_results = rag_results
                    except Exception:  # nosec B110 - RAG errors are non-fatal
                        pass

            # ── Web search ─────────────────────────────────────────────────
            if state.search_enabled:
                if thinking is not None:
                    thinking.set_context("Searching the web…")
                backend = self._ctx.search_registry.get_available(self._ctx.config.search_provider)
                if backend is not None:
                    try:
                        results = await backend.search(query)
                        if results:
                            state.history[-1] = ChatMessage(
                                role="user",
                                content=[
                                    TextPart(_format_search_results(results, query)),
                                    TextPart(query),
                                ],
                            )
                    except SearchError:
                        pass

            # Replace ThinkingWidget with the real AIBubble before first token
            if thinking is not None:
                thinking.stop()
                await thinking.remove()
            conv = self.query_one(ConversationView)
            conv.add_bubble(bubble)

            if thinking is not None:
                thinking = None  # prevent double-remove in error path

            chunk_stream = state.provider.stream_chat(
                messages=_trim_history(state.history, state.context_window),
                model=state.model_id,
                gen_params=state.gen_params,
            )
            _last_usage = None
            async for chunk in chunk_stream:
                if self._stop_streaming:
                    _was_stopped = True
                    break
                if chunk.text:
                    buffer += chunk.text
                    bubble.append_text(chunk.text)
                if chunk.usage:
                    # Accumulate across turns — do not overwrite
                    state.total_tokens_used += chunk.usage.total_tokens
                    state.tokens_estimated = False
                    _got_usage = True
                    _last_usage = chunk.usage

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

    async def _rebuild_rag_index(self, index_name: str) -> None:
        """Background worker: rebuild a named RAG index."""
        t = self._ctx.theme
        conv = self.query_one(ConversationView)
        emb = self._ctx.embedding_registry.get_available(self._ctx.config.embedding_backend)
        if emb is None:
            conv.add_bubble(
                SystemBubble(
                    "No embedding backend available. Install anythink[rag].", t, kind="error"
                )
            )
            return
        try:
            info = await self._ctx.rag_manager.build_index(index_name, emb)
            conv.add_bubble(
                SystemBubble(
                    f"\U0001f4da Index '{index_name}' rebuilt: "
                    f"{info.chunk_count:,} chunks from {info.file_count} files.",
                    t,
                    kind="success",
                )
            )
            if self._state is not None:
                self.query_one(HUDWidget).update_from_state(self._ctx, self._state)
            self._ctx.notifier.notify(
                "rag_build_done",
                "Anythink — RAG Build Complete",
                f"'{index_name}': {info.chunk_count:,} chunks.",
            )
        except Exception as exc:  # nosec B110 - rebuild errors surfaced to user
            conv.add_bubble(SystemBubble(f"Rebuild failed: {exc}", t, kind="error"))

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
        header = f"⚙️  {language} · exit {result.exit_code} · {result.duration_s:.3f}s"
        body_parts = [header, f"stdout:\n{stdout_text}"]
        if stderr_text:
            body_parts.append(f"stderr:\n{stderr_text}")

        kind = "code" if result.succeeded else "error"
        conv.add_bubble(SystemBubble("\n".join(body_parts), t, kind=kind))
        self._log_tool_event(language, "exec", stdout_text[:120])
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

        ai_bubble = AIBubble(t, model_alias=state.model_id, provider=state.provider.display_name)
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

        ai_bubble = AIBubble(t, model_alias=state.model_id, provider=state.provider.display_name)
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
        preview = result.content[:600] + ("…" if len(result.content) > 600 else "")
        kind = "error" if result.is_error else "code"
        conv.add_bubble(SystemBubble(f"{header}\n{preview}", t, kind=kind))
        self._log_tool_event(tool_name, result.server_name or "mcp", result.content[:120])

        if result.is_error:
            return

        result_ctx = (
            f"[MCP Tool: {tool_name} on {result.server_name}, {result.duration_s:.3f}s]\n"
            f"{result.content}"
        )
        self._undo_checkpoints.append(len(state.history))
        state.history.append(ChatMessage(role="user", content=result_ctx))

        ai_bub = AIBubble(t, model_alias=state.model_id, provider=state.provider.display_name)
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
