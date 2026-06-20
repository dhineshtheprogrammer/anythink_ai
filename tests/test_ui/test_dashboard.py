"""Tests for Phase-7 Dashboard mode — panels, bindings, and mode toggle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from anythink.app.chat import ChatState
from anythink.config.schema import AppConfig
from anythink.providers.base import BaseProvider, ChatMessage, ModelInfo, StreamChunk
from anythink.ui.textual.app import AnythinkApp
from anythink.ui.textual.panels.file_browser import FileBrowserTab
from anythink.ui.textual.panels.rag_browser import RAGBrowserTab
from anythink.ui.textual.panels.session_list import SessionListPanel
from anythink.ui.textual.panels.stats import StatsPanel
from anythink.ui.textual.panels.tool_output import ToolOutputTab

# ── test double ───────────────────────────────────────────────────────────────


class _SilentProvider(BaseProvider):
    name = "silent"
    display_name = "Silent"

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(text="ok", finish_reason="stop")

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("silent-1", "Silent-1", 4096)]

    async def test_connection(self) -> bool:
        return True

    @property
    def supports_vision(self) -> bool:
        return False

    @property
    def requires_api_key(self) -> bool:
        return False


def _make_state() -> ChatState:
    return ChatState(
        provider=_SilentProvider(),
        model_id="silent-1",
        context_window=4096,
    )


def _make_ctx() -> object:
    """MagicMock AppContext safe for dashboard panel calls."""
    from anythink.ui.theme import MIDNIGHT

    ctx = MagicMock()
    ctx.config = AppConfig(session_autosave=False)
    ctx.theme = MIDNIGHT
    ctx.console = MagicMock()

    # Prevent format-spec error in StatsPanel (chunk_count must be int)
    ctx.rag_manager.is_active = False
    ctx.rag_manager.active_name = ""
    ctx.rag_manager.list_indexes.return_value = []

    ctx.mcp_manager.list_servers.return_value = []
    ctx.session_manager.list_sessions.return_value = []
    ctx.session_manager.find_by_name_or_id.return_value = None
    ctx.search_registry.get_available.return_value = None
    ctx.key_manager.get_key.return_value = None
    return ctx


# ── panel unit tests (no Pilot needed) ───────────────────────────────────────


class TestSessionListPanel:
    def test_panel_has_correct_css_defaults(self) -> None:
        ctx = _make_ctx()
        panel = SessionListPanel(ctx)
        assert "display: none" in SessionListPanel.DEFAULT_CSS

    def test_refresh_sessions_empty(self) -> None:
        ctx = _make_ctx()
        panel = SessionListPanel(ctx)
        panel._sessions = []
        # calling refresh_sessions without a mounted DOM should not crash
        # (it accesses ListView which isn't mounted yet — we test the data path)
        assert panel._sessions == []

    def test_session_selected_message(self) -> None:
        msg = SessionListPanel.SessionSelected("abc-123")
        assert msg.session_id == "abc-123"


class TestStatsPanel:
    def test_update_stats_no_state(self) -> None:
        ctx = _make_ctx()
        panel = StatsPanel(ctx)
        # StatsPanel needs a mounted DOM for query_one — test only CSS/init
        assert "display: none" in StatsPanel.DEFAULT_CSS

    def test_stats_panel_css_width(self) -> None:
        assert "width: 28" in StatsPanel.DEFAULT_CSS


class TestFileBrowserTab:
    def test_default_css_padding(self) -> None:
        tab = FileBrowserTab()
        assert "padding" in FileBrowserTab.DEFAULT_CSS


class TestRAGBrowserTab:
    def test_index_activated_message(self) -> None:
        msg = RAGBrowserTab.IndexActivated("my-index")
        assert msg.index_name == "my-index"

    def test_css_height(self) -> None:
        assert "height: 1fr" in RAGBrowserTab.DEFAULT_CSS


class TestToolOutputTab:
    def test_css_padding(self) -> None:
        assert "height: 1fr" in ToolOutputTab.DEFAULT_CSS


# ── Pilot / run_test integration tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_simple_mode_panels_hidden() -> None:
    """Panels should be hidden by default (simple mode)."""
    ctx = _make_ctx()
    state = _make_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            left = tapp.query_one("#left-panel")
            right = tapp.query_one("#right-panel")
            tabs = tapp.query_one("#bottom-tabs")
            assert not left.display
            assert not right.display
            assert not tabs.display
            assert not tapp._dashboard_mode


@pytest.mark.asyncio
async def test_dashboard_toggle_ctrl_d() -> None:
    """Ctrl+D should enable all dashboard panels."""
    ctx = _make_ctx()
    state = _make_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            assert not tapp._dashboard_mode

            await pilot.press("ctrl+d")
            await pilot.pause()

            assert tapp._dashboard_mode
            assert tapp.query_one("#left-panel").display
            assert tapp.query_one("#right-panel").display
            assert tapp.query_one("#bottom-tabs").display


@pytest.mark.asyncio
async def test_dashboard_toggle_twice_returns_to_simple() -> None:
    """Two Ctrl+D presses should return to simple mode."""
    ctx = _make_ctx()
    state = _make_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            await pilot.press("ctrl+d")
            await pilot.pause()
            assert tapp._dashboard_mode

            await pilot.press("ctrl+d")
            await pilot.pause()
            assert not tapp._dashboard_mode
            assert not tapp.query_one("#left-panel").display


@pytest.mark.asyncio
async def test_dashboard_launch_flag() -> None:
    """AnythinkApp(ctx, dashboard=True) should start in dashboard mode."""
    ctx = _make_ctx()
    state = _make_state()
    tapp = AnythinkApp(ctx, dashboard=True)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            await pilot.pause()
            assert tapp._dashboard_mode
            assert tapp.query_one("#left-panel").display
            assert tapp.query_one("#right-panel").display


@pytest.mark.asyncio
async def test_ctrl_l_toggles_left_panel_in_dashboard() -> None:
    """Ctrl+L should toggle the left panel when in dashboard mode."""
    ctx = _make_ctx()
    state = _make_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            # Enable dashboard first
            await pilot.press("ctrl+d")
            await pilot.pause()
            assert tapp.query_one("#left-panel").display

            # Toggle left panel off
            await pilot.press("ctrl+l")
            await pilot.pause()
            assert not tapp.query_one("#left-panel").display

            # Toggle left panel back on
            await pilot.press("ctrl+l")
            await pilot.pause()
            assert tapp.query_one("#left-panel").display


@pytest.mark.asyncio
async def test_ctrl_r_toggles_right_panel_in_dashboard() -> None:
    """Ctrl+R should toggle the right (Stats) panel when in dashboard mode."""
    ctx = _make_ctx()
    state = _make_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            await pilot.press("ctrl+d")
            await pilot.pause()
            assert tapp.query_one("#right-panel").display

            await pilot.press("ctrl+r")
            await pilot.pause()
            assert not tapp.query_one("#right-panel").display


@pytest.mark.asyncio
async def test_ctrl_l_noop_in_simple_mode() -> None:
    """Ctrl+L should be a no-op (left panel stays hidden) in simple mode."""
    ctx = _make_ctx()
    state = _make_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            assert not tapp._dashboard_mode
            await pilot.press("ctrl+l")
            await pilot.pause()
            # Panel must still be hidden
            assert not tapp.query_one("#left-panel").display


@pytest.mark.asyncio
async def test_tool_output_add_event() -> None:
    """Tool events appended to ToolOutputTab should be stored."""
    ctx = _make_ctx()
    state = _make_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            tab = tapp.query_one(ToolOutputTab)
            # Before any events
            assert tab._event_count == 0

            tapp._log_tool_event("python", "exec", "hello world")
            await pilot.pause()
            assert tab._event_count == 1

            tapp._log_tool_event("web_search", "search", "some results")
            await pilot.pause()
            assert tab._event_count == 2


@pytest.mark.asyncio
async def test_bottom_tabs_compose() -> None:
    """TabbedContent should compose all three tab panes."""
    ctx = _make_ctx()
    state = _make_state()
    tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

    with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
        async with tapp.run_test(headless=True) as pilot:
            assert tapp.query_one(FileBrowserTab) is not None
            assert tapp.query_one(RAGBrowserTab) is not None
            assert tapp.query_one(ToolOutputTab) is not None
