"""Tests for the ScheduleRunner."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anythink.schedule.models import ScheduledPrompt
from anythink.schedule.runner import ScheduleRunner, _is_due

# ── helpers ────────────────────────────────────────────────────────────────────


def _make_ctx(tmp_path: Path) -> MagicMock:
    """Build a minimal mock AppContext for schedule runner tests."""
    from anythink.providers.base import StreamChunk, TokenUsage

    async def _stream(*args, **kwargs) -> AsyncIterator[StreamChunk]:
        usage = TokenUsage(prompt_tokens=5, completion_tokens=10, total_tokens=15)
        yield StreamChunk(text="Hello ", finish_reason=None)
        yield StreamChunk(text="world", finish_reason="stop", usage=usage)

    mock_provider = MagicMock()
    mock_provider.stream_chat = _stream

    mock_alias = MagicMock()
    mock_alias.provider = "openai"
    mock_alias.model_id = "gpt-4o"
    mock_alias.gen_params = None

    ctx = MagicMock()
    ctx.config.default_model_alias = "test-alias"
    ctx.config.spend_tracking = False
    ctx.model_registry.get.return_value = mock_alias
    ctx.key_manager.get_key.return_value = "test-key"
    ctx.provider_registry.get.return_value = lambda api_key, **kw: mock_provider
    ctx.notifier.notify = MagicMock()
    ctx.schedule_manager.update_last_run = MagicMock()
    return ctx


def _make_schedule(**kwargs) -> ScheduledPrompt:
    defaults = {
        "name": "test-sched",
        "cron_expr": "* * * * *",  # every minute
        "prompt": "Say hello",
        "alias": None,
        "output_file": None,
        "enabled": True,
    }
    defaults.update(kwargs)
    return ScheduledPrompt(**defaults)  # type: ignore[arg-type]


# ── _is_due tests ──────────────────────────────────────────────────────────────


class TestIsDue:
    def test_never_run_is_always_due(self) -> None:
        pytest.importorskip("croniter")
        s = _make_schedule(last_run=None)
        assert _is_due(s, datetime.now(UTC)) is True

    def test_disabled_schedule_never_due(self) -> None:
        s = _make_schedule(enabled=False, last_run=None)
        assert _is_due(s, datetime.now(UTC)) is False

    def test_recently_run_not_due(self) -> None:
        pytest.importorskip("croniter")
        # Daily at midnight — not due if last_run was today already
        now = datetime(2025, 6, 22, 10, 0, tzinfo=UTC)
        last = datetime(2025, 6, 22, 0, 1, tzinfo=UTC)
        s = _make_schedule(cron_expr="0 0 * * *", last_run=last)
        assert _is_due(s, now) is False

    def test_overdue_is_due(self) -> None:
        pytest.importorskip("croniter")
        # Daily at 9am — if it ran yesterday at 9am, it's due today
        now = datetime(2025, 6, 22, 10, 0, tzinfo=UTC)
        last = datetime(2025, 6, 21, 9, 1, tzinfo=UTC)
        s = _make_schedule(cron_expr="0 9 * * *", last_run=last)
        assert _is_due(s, now) is True

    def test_invalid_cron_not_due(self) -> None:
        s = _make_schedule(cron_expr="not a cron expression")
        # Should return False rather than raising
        result = _is_due(s, datetime.now(UTC))
        assert result is False

    def test_naive_last_run_normalised(self) -> None:
        pytest.importorskip("croniter")
        now = datetime(2025, 6, 22, 10, 0, tzinfo=UTC)
        # Naive datetime (no tzinfo) — should be treated as UTC
        last = datetime(2025, 6, 21, 9, 0)  # naive, yesterday
        s = _make_schedule(cron_expr="0 9 * * *", last_run=last)
        assert _is_due(s, now) is True


# ── ScheduleRunner.run_once ────────────────────────────────────────────────────


class TestRunOnce:
    async def test_basic_run_returns_text(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        runner = ScheduleRunner(ctx)
        s = _make_schedule()
        result = await runner.run_once(s)
        assert result == "Hello world"

    async def test_updates_last_run(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        runner = ScheduleRunner(ctx)
        s = _make_schedule()
        await runner.run_once(s)
        ctx.schedule_manager.update_last_run.assert_called_once()
        call_name = ctx.schedule_manager.update_last_run.call_args[0][0]
        assert call_name == "test-sched"

    async def test_sends_notification(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        runner = ScheduleRunner(ctx)
        s = _make_schedule()
        await runner.run_once(s)
        ctx.notifier.notify.assert_called_once()

    async def test_writes_output_file(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        runner = ScheduleRunner(ctx)
        out = tmp_path / "out.txt"
        s = _make_schedule(output_file=str(out))
        await runner.run_once(s)
        assert out.exists()
        content = out.read_text()
        assert "Hello world" in content

    async def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        runner = ScheduleRunner(ctx)
        out = tmp_path / "out.txt"
        out.write_text("previous content\n")
        s = _make_schedule(output_file=str(out))
        await runner.run_once(s)
        content = out.read_text()
        assert "previous content" in content
        assert "Hello world" in content

    async def test_missing_alias_raises(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        ctx.config.default_model_alias = None
        ctx.model_registry.get.return_value = None
        runner = ScheduleRunner(ctx)
        s = _make_schedule(alias=None)
        with pytest.raises(ValueError, match="no default model"):
            await runner.run_once(s)

    async def test_unknown_alias_raises(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        ctx.model_registry.get.return_value = None
        runner = ScheduleRunner(ctx)
        s = _make_schedule(alias="nonexistent")
        with pytest.raises(ValueError, match="not found"):
            await runner.run_once(s)

    async def test_unknown_provider_raises(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        ctx.provider_registry.get.return_value = None
        runner = ScheduleRunner(ctx)
        s = _make_schedule()
        with pytest.raises(ValueError, match="not registered"):
            await runner.run_once(s)


# ── ScheduleRunner.run_all_due ─────────────────────────────────────────────────


class TestRunAllDue:
    async def test_empty_schedule_list(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        ctx.schedule_manager.list_all.return_value = []
        runner = ScheduleRunner(ctx)
        results = await runner.run_all_due()
        assert results == []

    async def test_due_schedule_fires(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        s = _make_schedule(last_run=None)  # never run = always due
        ctx.schedule_manager.list_all.return_value = [s]
        runner = ScheduleRunner(ctx)

        with patch.object(runner, "_is_due_wrapper", return_value=True, create=True):
            pass  # _is_due_wrapper doesn't exist; patch _is_due module-level fn instead

        # Patch _is_due at module level to avoid croniter dependency in this test
        with patch("anythink.schedule.runner._is_due", return_value=True):
            results = await runner.run_all_due()

        assert len(results) == 1
        name, ok, _summary = results[0]
        assert name == "test-sched"
        assert ok is True

    async def test_non_due_schedule_skipped(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        s = _make_schedule()
        ctx.schedule_manager.list_all.return_value = [s]
        runner = ScheduleRunner(ctx)

        with patch("anythink.schedule.runner._is_due", return_value=False):
            results = await runner.run_all_due()

        assert results == []

    async def test_error_in_one_schedule_captured(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        s = _make_schedule()
        ctx.schedule_manager.list_all.return_value = [s]
        ctx.provider_registry.get.return_value = None  # will cause ValueError in run_once
        runner = ScheduleRunner(ctx)

        with patch("anythink.schedule.runner._is_due", return_value=True):
            results = await runner.run_all_due()

        assert len(results) == 1
        name, ok, _msg = results[0]
        assert name == "test-sched"
        assert ok is False

    async def test_multiple_due_schedules_all_fire(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        schedules = [_make_schedule(name=f"s{i}") for i in range(3)]
        ctx.schedule_manager.list_all.return_value = schedules
        runner = ScheduleRunner(ctx)

        with patch("anythink.schedule.runner._is_due", return_value=True):
            results = await runner.run_all_due()

        assert len(results) == 3
        assert all(ok for _, ok, _ in results)
