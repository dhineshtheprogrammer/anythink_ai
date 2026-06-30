"""Tests for WorkflowPanel — the MMWE live-progress side panel (Phase 11)."""

from __future__ import annotations

import pytest

from anythink.ui.textual.panels.workflow_panel import WorkflowPanel

# ---------------------------------------------------------------------------
# CSS / structure tests (no pilot needed)
# ---------------------------------------------------------------------------


class TestWorkflowPanelCSS:
    """Verify the DEFAULT_CSS matches the DebugPanel convention."""

    def test_display_none_by_default(self) -> None:
        assert "display: none" in WorkflowPanel.DEFAULT_CSS

    def test_width_36(self) -> None:
        assert "width: 36" in WorkflowPanel.DEFAULT_CSS

    def test_has_border_left(self) -> None:
        assert "border-left" in WorkflowPanel.DEFAULT_CSS

    def test_has_header_style(self) -> None:
        assert "#wp-header" in WorkflowPanel.DEFAULT_CSS

    def test_has_stage_start_class(self) -> None:
        assert ".wp-stage-start" in WorkflowPanel.DEFAULT_CSS

    def test_has_stage_ok_class(self) -> None:
        assert ".wp-stage-ok" in WorkflowPanel.DEFAULT_CSS

    def test_has_stage_err_class(self) -> None:
        assert ".wp-stage-err" in WorkflowPanel.DEFAULT_CSS

    def test_has_approval_class(self) -> None:
        assert ".wp-approval" in WorkflowPanel.DEFAULT_CSS

    def test_has_done_class(self) -> None:
        assert ".wp-done" in WorkflowPanel.DEFAULT_CSS


# ---------------------------------------------------------------------------
# Async API tests (Textual Pilot)
# ---------------------------------------------------------------------------

# Minimal CSS variable set so WorkflowPanel's $accent/$muted/$success etc. resolve.
_THEME_VARS: dict[str, str] = {
    "primary": "#cccccc",
    "secondary": "#aaaaaa",
    "accent": "#00d7ff",
    "muted": "#888888",
    "error": "#ff5555",
    "warning": "#ffff55",
    "success": "#55ff55",
    "info": "#5588ff",
    "background": "#0d0d0d",
    "surface": "#1a1a1a",
}


@pytest.fixture()
def panel_app():
    """Return a minimal App that contains only WorkflowPanel."""
    from textual.app import App, ComposeResult

    class _App(App):  # type: ignore[type-arg]
        def get_css_variables(self) -> dict[str, str]:
            base = super().get_css_variables()
            base.update(_THEME_VARS)
            return base

        def compose(self) -> ComposeResult:
            wp = WorkflowPanel(id="wp")
            wp.display = True
            yield wp

    return _App()


@pytest.mark.asyncio
async def test_panel_mounts_header(panel_app) -> None:
    """WorkflowPanel should mount with the default header text."""
    from textual.widgets import Static

    async with panel_app.run_test(headless=True) as pilot:
        header = panel_app.query_one("#wp-header", Static)
        assert "Workflow" in header.content


@pytest.mark.asyncio
async def test_begin_workflow_updates_header(panel_app) -> None:
    """begin_workflow() should display the workflow name in the header."""
    from textual.widgets import Static

    async with panel_app.run_test(headless=True) as pilot:
        wp = panel_app.query_one(WorkflowPanel)
        await wp.begin_workflow("my-pipeline")
        await pilot.pause(0.1)
        header = panel_app.query_one("#wp-header", Static)
        assert "my-pipeline" in header.content


@pytest.mark.asyncio
async def test_stage_started_appends_line(panel_app) -> None:
    """stage_started() should add a new Static line to the log."""
    from textual.containers import VerticalScroll
    from textual.widgets import Static

    async with panel_app.run_test(headless=True) as pilot:
        wp = panel_app.query_one(WorkflowPanel)
        await wp.begin_workflow("pipe")
        await pilot.pause(0.05)

        before = len(list(panel_app.query_one("#wp-log", VerticalScroll).query(Static)))
        await wp.stage_started("s1", "Fetch data")
        await pilot.pause(0.05)
        after = len(list(panel_app.query_one("#wp-log", VerticalScroll).query(Static)))

        assert after > before


@pytest.mark.asyncio
async def test_stage_complete_ok_appends_check(panel_app) -> None:
    """stage_complete(ok=True) should add a line containing the ✓ symbol."""
    from textual.containers import VerticalScroll
    from textual.widgets import Static

    async with panel_app.run_test(headless=True) as pilot:
        wp = panel_app.query_one(WorkflowPanel)
        await wp.begin_workflow("pipe")
        await wp.stage_complete("s1", ok=True, summary="done")
        await pilot.pause(0.1)

        texts = [s.content for s in panel_app.query_one("#wp-log", VerticalScroll).query(Static)]
        assert any("✓" in t for t in texts)


@pytest.mark.asyncio
async def test_stage_complete_error_appends_x(panel_app) -> None:
    """stage_complete(ok=False) should add a line containing the ✗ symbol."""
    from textual.containers import VerticalScroll
    from textual.widgets import Static

    async with panel_app.run_test(headless=True) as pilot:
        wp = panel_app.query_one(WorkflowPanel)
        await wp.begin_workflow("pipe")
        await wp.stage_complete("s1", ok=False)
        await pilot.pause(0.1)

        texts = [s.content for s in panel_app.query_one("#wp-log", VerticalScroll).query(Static)]
        assert any("✗" in t for t in texts)


@pytest.mark.asyncio
async def test_approval_needed_appends_warning(panel_app) -> None:
    """approval_needed() should add two lines: the message and the hint."""
    from textual.containers import VerticalScroll
    from textual.widgets import Static

    async with panel_app.run_test(headless=True) as pilot:
        wp = panel_app.query_one(WorkflowPanel)
        await wp.begin_workflow("pipe")

        before = len(list(panel_app.query_one("#wp-log", VerticalScroll).query(Static)))
        await wp.approval_needed("Delete all records?")
        await pilot.pause(0.1)
        after = len(list(panel_app.query_one("#wp-log", VerticalScroll).query(Static)))

        assert after >= before + 2


@pytest.mark.asyncio
async def test_workflow_done_completed_resets_header(panel_app) -> None:
    """workflow_done('completed') should restore the default header text."""
    from textual.widgets import Static

    async with panel_app.run_test(headless=True) as pilot:
        wp = panel_app.query_one(WorkflowPanel)
        await wp.begin_workflow("pipe")
        await pilot.pause(0.05)
        await wp.workflow_done("completed", "All done.")
        await pilot.pause(0.1)

        header = panel_app.query_one("#wp-header", Static)
        assert "pipe" not in header.content


@pytest.mark.asyncio
async def test_workflow_done_appends_status(panel_app) -> None:
    """workflow_done() should add a COMPLETED banner line."""
    from textual.containers import VerticalScroll
    from textual.widgets import Static

    async with panel_app.run_test(headless=True) as pilot:
        wp = panel_app.query_one(WorkflowPanel)
        await wp.begin_workflow("pipe")
        await wp.workflow_done("completed")
        await pilot.pause(0.1)

        texts = [s.content for s in panel_app.query_one("#wp-log", VerticalScroll).query(Static)]
        assert any("COMPLETED" in t for t in texts)


@pytest.mark.asyncio
async def test_loop_progress_appends_fraction(panel_app) -> None:
    """loop_progress() should add an iteration count line."""
    from textual.containers import VerticalScroll
    from textual.widgets import Static

    async with panel_app.run_test(headless=True) as pilot:
        wp = panel_app.query_one(WorkflowPanel)
        await wp.begin_workflow("pipe")
        await wp.loop_progress(3, 10)
        await pilot.pause(0.1)

        texts = [s.content for s in panel_app.query_one("#wp-log", VerticalScroll).query(Static)]
        assert any("3/10" in t for t in texts)


@pytest.mark.asyncio
async def test_clear_resets_log(panel_app) -> None:
    """clear() should remove previous entries and restore the default header."""
    from textual.containers import VerticalScroll
    from textual.widgets import Static

    async with panel_app.run_test(headless=True) as pilot:
        wp = panel_app.query_one(WorkflowPanel)
        await wp.begin_workflow("pipe")
        await wp.stage_started("s1", "Step one")
        await pilot.pause(0.05)

        await wp.clear()
        await pilot.pause(0.1)

        header = panel_app.query_one("#wp-header", Static)
        assert "pipe" not in header.content
