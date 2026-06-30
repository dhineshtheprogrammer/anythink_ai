"""TUI integration tests for MMWE workflow wiring (Phase 11).

Covers:
- WorkflowPanel presence and initial visibility in the DOM
- Initial state flags set by __init__
- _dispatch_command action handling for all workflow actions
- _pending_workflow_approval gate (confirm flow)
- _handle_workflow_approval routing (plan-level vs stage-level)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest

from anythink.app.chat import ChatState
from anythink.config.schema import AppConfig
from anythink.providers.base import BaseProvider, ChatMessage, ModelInfo, StreamChunk
from anythink.ui.bubbles import SystemBubble
from anythink.ui.textual.app import AnythinkApp
from anythink.ui.textual.conversation import ConversationView
from anythink.ui.textual.panels.workflow_panel import WorkflowPanel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_ctx(autonomy_mode: str = "confirm") -> object:
    """MagicMock AppContext sufficient for workflow TUI tests."""
    ctx = MagicMock()
    ctx.config = AppConfig(
        session_autosave=False,
        workflow_autonomy_mode=autonomy_mode,
    )
    from anythink.ui.theme import MIDNIGHT

    ctx.theme = MIDNIGHT
    ctx.console = MagicMock()
    ctx.rag_manager.is_active = False
    ctx.rag_manager.active_name = ""
    ctx.rag_manager.list_indexes.return_value = []
    ctx.mcp_manager.list_servers.return_value = []
    ctx.session_manager.list_sessions.return_value = []
    ctx.session_manager.find_by_name_or_id.return_value = None
    ctx.search_registry.get_available.return_value = None
    ctx.key_manager.get_key.return_value = None
    ctx.workflow_storage._dir = MagicMock()
    ctx.workflow_storage._dir.__truediv__ = lambda self, other: MagicMock()
    return ctx


# ---------------------------------------------------------------------------
# DOM composition tests
# ---------------------------------------------------------------------------


class TestWorkflowPanelInDOM:
    """WorkflowPanel must be composed into the app layout."""

    @pytest.mark.asyncio
    async def test_workflow_panel_is_in_dom(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                wp = tapp.query_one("#workflow-panel")
                assert wp is not None

    @pytest.mark.asyncio
    async def test_workflow_panel_is_hidden_by_default(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                wp = tapp.query_one("#workflow-panel")
                assert not wp.display

    @pytest.mark.asyncio
    async def test_workflow_panel_is_workflow_panel_instance(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                assert isinstance(tapp.query_one("#workflow-panel"), WorkflowPanel)


# ---------------------------------------------------------------------------
# __init__ state flag tests (no pilot needed)
# ---------------------------------------------------------------------------


class TestWorkflowStateFlags:
    """MMWE state flags must be initialised correctly."""

    def test_pending_workflow_approval_is_none(self) -> None:
        ctx = _make_ctx()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]
        assert tapp._pending_workflow_approval is None

    def test_workflow_state_is_none(self) -> None:
        ctx = _make_ctx()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]
        assert tapp._workflow_state is None

    def test_workflow_approval_result_default(self) -> None:
        ctx = _make_ctx()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]
        assert tapp._workflow_approval_result == "aborted"

    def test_workflow_approval_event_is_asyncio_event(self) -> None:
        import asyncio

        ctx = _make_ctx()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]
        assert isinstance(tapp._workflow_approval_event, asyncio.Event)


# ---------------------------------------------------------------------------
# _dispatch_command action tests (Pilot)
# ---------------------------------------------------------------------------


class TestWorkflowDispatchNoRunning:
    """Dispatching stop/pause/resume when no workflow is running shows info bubble."""

    @pytest.mark.asyncio
    async def test_workflow_stop_no_workflow(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                from anythink.commands.base import CommandResult

                result = CommandResult(action="workflow_stop")
                await tapp._dispatch_command.__func__(tapp, "/workflow stop")  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_workflow_stop_directly(self) -> None:
        """Directly set _workflow_state to None and dispatch to verify bubble."""
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                tapp._workflow_state = None
                await pilot.press("enter")  # dismiss naming prompt
                await pilot.pause(0.05)

                # Type /workflow stop
                for ch in "/workflow stop":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.2)

                conv = tapp.query_one(ConversationView)
                bubbles = list(conv.query(SystemBubble))
                texts = [b._message for b in bubbles]
                assert any("No workflow" in t for t in texts)

    @pytest.mark.asyncio
    async def test_workflow_pause_no_workflow(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                tapp._workflow_state = None
                await pilot.press("enter")
                await pilot.pause(0.05)
                for ch in "/workflow pause":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.2)

                conv = tapp.query_one(ConversationView)
                texts = [b._message for b in conv.query(SystemBubble)]
                assert any("No workflow" in t for t in texts)

    @pytest.mark.asyncio
    async def test_workflow_resume_no_workflow(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                tapp._workflow_state = None
                await pilot.press("enter")
                await pilot.pause(0.05)
                for ch in "/workflow resume":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.2)

                conv = tapp.query_one(ConversationView)
                texts = [b._message for b in conv.query(SystemBubble)]
                assert any("No workflow" in t for t in texts)


class TestWorkflowDispatchWithRunning:
    """Dispatching stop/pause/resume when a workflow IS running mutates state."""

    @pytest.mark.asyncio
    async def test_workflow_stop_sets_flag(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                from anythink.workflow.models import WorkflowPlan, WorkflowState

                plan = WorkflowPlan(name="p", trigger="t")
                ws = WorkflowState(plan=plan)
                tapp._workflow_state = ws

                await pilot.press("enter")
                await pilot.pause(0.05)
                for ch in "/workflow stop":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.2)

                assert ws.stop_requested is True

    @pytest.mark.asyncio
    async def test_workflow_pause_sets_flag(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                from anythink.workflow.models import WorkflowPlan, WorkflowState

                plan = WorkflowPlan(name="p", trigger="t")
                ws = WorkflowState(plan=plan)
                tapp._workflow_state = ws

                await pilot.press("enter")
                await pilot.pause(0.05)
                for ch in "/workflow pause":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.2)

                assert ws.paused is True

    @pytest.mark.asyncio
    async def test_workflow_resume_clears_flag(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                from anythink.workflow.models import WorkflowPlan, WorkflowState

                plan = WorkflowPlan(name="p", trigger="t")
                ws = WorkflowState(plan=plan)
                ws.paused = True
                tapp._workflow_state = ws

                await pilot.press("enter")
                await pilot.pause(0.05)
                for ch in "/workflow resume":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.2)

                assert ws.paused is False


class TestWorkflowDispatchMisc:
    """workflow_new_wizard, workflow_panel_toggle, open_file_in_editor."""

    @pytest.mark.asyncio
    async def test_workflow_new_wizard_shows_bubble(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                await pilot.press("enter")
                await pilot.pause(0.05)
                for ch in "/workflow new":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.2)

                conv = tapp.query_one(ConversationView)
                texts = [b._message for b in conv.query(SystemBubble)]
                assert any("workflow" in t.lower() for t in texts)

    @pytest.mark.asyncio
    async def test_workflow_panel_toggle_shows_panel(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                await pilot.pause(0.05)
                wp = tapp.query_one("#workflow-panel")
                assert not wp.display

                await pilot.press("enter")
                await pilot.pause(0.05)
                for ch in "/workflow panel":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.2)

                assert wp.display

    @pytest.mark.asyncio
    async def test_workflow_panel_toggle_twice_hides_panel(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                await pilot.press("enter")
                await pilot.pause(0.05)

                # Toggle on
                for ch in "/workflow panel":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.15)
                assert tapp.query_one("#workflow-panel").display

                # Toggle off
                for ch in "/workflow panel":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.15)
                assert not tapp.query_one("#workflow-panel").display


# ---------------------------------------------------------------------------
# workflow_status_request
# ---------------------------------------------------------------------------


class TestWorkflowStatus:
    @pytest.mark.asyncio
    async def test_status_no_workflow_shows_info(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                tapp._workflow_state = None
                await pilot.press("enter")
                await pilot.pause(0.05)
                for ch in "/workflow status":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.2)

                conv = tapp.query_one(ConversationView)
                texts = [b._message for b in conv.query(SystemBubble)]
                assert any("No workflow" in t for t in texts)

    @pytest.mark.asyncio
    async def test_status_with_workflow_shows_name(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                from anythink.workflow.models import WorkflowPlan, WorkflowState

                plan = WorkflowPlan(name="data-extract", trigger="Extract data")
                ws = WorkflowState(plan=plan)
                tapp._workflow_state = ws

                await pilot.press("enter")
                await pilot.pause(0.05)
                for ch in "/workflow status":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.2)

                conv = tapp.query_one(ConversationView)
                texts = [b._message for b in conv.query(SystemBubble)]
                assert any("data-extract" in t for t in texts)


# ---------------------------------------------------------------------------
# _handle_workflow_approval — plan-level gate
# ---------------------------------------------------------------------------


class TestHandleWorkflowApproval:
    """_handle_workflow_approval for plan-level confirm and stage-level gate."""

    @pytest.mark.asyncio
    async def test_cancel_clears_pending_flag(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                from anythink.workflow.models import WorkflowPlan

                plan = WorkflowPlan(name="p", trigger="t")
                tapp._pending_workflow_approval = {"plan": plan}

                await tapp._handle_workflow_approval("n")
                await pilot.pause(0.05)

                assert tapp._pending_workflow_approval is None

    @pytest.mark.asyncio
    async def test_cancel_shows_cancelled_bubble(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                from anythink.workflow.models import WorkflowPlan

                plan = WorkflowPlan(name="p", trigger="t")
                tapp._pending_workflow_approval = {"plan": plan}

                await tapp._handle_workflow_approval("n")
                await pilot.pause(0.1)

                conv = tapp.query_one(ConversationView)
                texts = [b._message for b in conv.query(SystemBubble)]
                assert any("cancel" in t.lower() for t in texts)

    @pytest.mark.asyncio
    async def test_confirm_yes_fires_worker(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        workers_fired: list[str] = []

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                from anythink.workflow.models import WorkflowPlan

                plan = WorkflowPlan(name="my-wf", trigger="t")
                tapp._pending_workflow_approval = {"plan": plan}

                with patch.object(
                    tapp, "_execute_workflow", side_effect=lambda p: workers_fired.append(p.name)
                ):
                    # _execute_workflow is called via run_worker — patch run_worker instead
                    with patch.object(tapp, "run_worker") as mock_rw:
                        await tapp._handle_workflow_approval("y")
                        await pilot.pause(0.1)
                        assert mock_rw.called

    @pytest.mark.asyncio
    async def test_stage_gate_approved_sets_result(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                tapp._pending_workflow_approval = {"approval_gate": True}
                tapp._workflow_approval_event.clear()

                await tapp._handle_workflow_approval("y")
                await pilot.pause(0.1)

                assert tapp._workflow_approval_result == "approved"
                assert tapp._pending_workflow_approval is None

    @pytest.mark.asyncio
    async def test_stage_gate_skip_sets_result(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                tapp._pending_workflow_approval = {"approval_gate": True}
                tapp._workflow_approval_event.clear()

                await tapp._handle_workflow_approval("skip")
                await pilot.pause(0.1)

                assert tapp._workflow_approval_result == "skipped"

    @pytest.mark.asyncio
    async def test_stage_gate_abort_sets_result(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                tapp._pending_workflow_approval = {"approval_gate": True}
                tapp._workflow_approval_event.clear()

                await tapp._handle_workflow_approval("n")
                await pilot.pause(0.1)

                assert tapp._workflow_approval_result == "aborted"

    @pytest.mark.asyncio
    async def test_stage_gate_fires_event(self) -> None:
        ctx = _make_ctx()
        state = _make_state()
        tapp = AnythinkApp(ctx)  # type: ignore[arg-type]

        with patch("anythink.app.chat.ChatApp._resolve_state", return_value=state):
            async with tapp.run_test(headless=True) as pilot:
                tapp._pending_workflow_approval = {"approval_gate": True}
                tapp._workflow_approval_event.clear()

                assert not tapp._workflow_approval_event.is_set()
                await tapp._handle_workflow_approval("y")
                await pilot.pause(0.1)

                assert tapp._workflow_approval_event.is_set()
