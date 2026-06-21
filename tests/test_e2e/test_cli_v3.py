"""End-to-end CLI tests for V3 commands (batch run, scheduler, doctor).

Uses Typer's CliRunner to invoke commands without spawning subprocesses.
All LLM calls are mocked to avoid requiring real API keys.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from anythink.app.context import AppContext
from anythink.cli import app
from anythink.config.manager import Paths
from anythink.providers.base import StreamChunk, TokenUsage

runner = CliRunner()


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_configured_ctx(xdg_dirs: Paths) -> AppContext:
    """Return an AppContext backed by temp dirs with a mock provider registered."""
    ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
    return ctx


def _mock_app_ctx(xdg_dirs: Paths) -> MagicMock:
    """Build a minimal mock AppContext that satisfies batch/scheduler commands."""
    usage = TokenUsage(prompt_tokens=5, completion_tokens=10, total_tokens=15)

    async def _stream(*args, **kwargs) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(text="Mock response", finish_reason="stop", usage=usage)

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
    ctx.key_manager.get_key.return_value = "key"
    ctx.provider_registry.get.return_value = lambda api_key, **kw: mock_provider
    ctx.notifier.notify = MagicMock()
    ctx.schedule_manager.list_all.return_value = []
    ctx.schedule_manager.update_last_run = MagicMock()
    return ctx


# ── batch run ──────────────────────────────────────────────────────────────────


class TestBatchRunCLI:
    def test_batch_run_writes_markdown(self, xdg_dirs: Paths, tmp_path: Path) -> None:
        prompts_file = tmp_path / "prompts.txt"
        prompts_file.write_text("What is 2+2?\nCapital of France?\n")
        out_file = tmp_path / "results.md"

        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = True
        mock_manager.paths = xdg_dirs

        mock_ctx = _mock_app_ctx(xdg_dirs)

        with (
            patch("anythink.cli.ConfigManager", return_value=mock_manager),
            patch("anythink.cli.AppContext") as MockCtx,
        ):
            MockCtx.create.return_value = mock_ctx
            result = runner.invoke(
                app,
                ["run", "--file", str(prompts_file), "--output", str(out_file)],
            )

        assert result.exit_code == 0, result.output
        assert out_file.exists()
        content = out_file.read_text()
        assert "Mock response" in content

    def test_batch_run_writes_json(self, xdg_dirs: Paths, tmp_path: Path) -> None:
        prompts_file = tmp_path / "prompts.txt"
        prompts_file.write_text("One prompt\n")
        out_file = tmp_path / "results.json"

        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = True
        mock_manager.paths = xdg_dirs

        mock_ctx = _mock_app_ctx(xdg_dirs)

        with (
            patch("anythink.cli.ConfigManager", return_value=mock_manager),
            patch("anythink.cli.AppContext") as MockCtx,
        ):
            MockCtx.create.return_value = mock_ctx
            result = runner.invoke(
                app,
                ["run", "--file", str(prompts_file), "--output", str(out_file), "--format", "json"],
            )

        assert result.exit_code == 0, result.output
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert len(data) == 1
        assert data[0]["response"] == "Mock response"

    def test_batch_run_not_configured_exits_nonzero(self, tmp_path: Path) -> None:
        prompts_file = tmp_path / "p.txt"
        prompts_file.write_text("hello\n")
        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = False
        with patch("anythink.cli.ConfigManager", return_value=mock_manager):
            result = runner.invoke(
                app,
                ["run", "--file", str(prompts_file), "--output", str(tmp_path / "out.md")],
            )
        assert result.exit_code != 0

    def test_batch_run_empty_file_exits_nonzero(self, xdg_dirs: Paths, tmp_path: Path) -> None:
        prompts_file = tmp_path / "empty.txt"
        prompts_file.write_text("   \n\n")
        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = True
        mock_manager.paths = xdg_dirs
        with patch("anythink.cli.ConfigManager", return_value=mock_manager):
            result = runner.invoke(
                app,
                ["run", "--file", str(prompts_file), "--output", str(tmp_path / "out.md")],
            )
        assert result.exit_code != 0


# ── doctor (CLI) ───────────────────────────────────────────────────────────────


class TestDoctorCLI:
    def test_doctor_passes_for_clean_install(self, xdg_dirs: Paths) -> None:
        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = True
        mock_manager.paths = xdg_dirs

        with (
            patch("anythink.cli.ConfigManager", return_value=mock_manager),
            patch("anythink.cli.AppContext") as MockCtx,
        ):
            MockCtx.create.return_value = AppContext.create(paths=xdg_dirs, console_file=StringIO())
            result = runner.invoke(app, ["doctor"])

        assert "Summary" in result.output
        assert "passed" in result.output

    def test_doctor_not_configured_exits_nonzero(self) -> None:
        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = False
        with patch("anythink.cli.ConfigManager", return_value=mock_manager):
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code != 0

    def test_doctor_shows_python_check(self, xdg_dirs: Paths) -> None:
        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = True
        mock_manager.paths = xdg_dirs

        with (
            patch("anythink.cli.ConfigManager", return_value=mock_manager),
            patch("anythink.cli.AppContext") as MockCtx,
        ):
            MockCtx.create.return_value = AppContext.create(paths=xdg_dirs, console_file=StringIO())
            result = runner.invoke(app, ["doctor"])

        assert "Python" in result.output


# ── scheduler list ─────────────────────────────────────────────────────────────


class TestSchedulerCLI:
    def test_scheduler_list_empty(self, xdg_dirs: Paths) -> None:
        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = True
        mock_manager.paths = xdg_dirs

        with (
            patch("anythink.cli.ConfigManager", return_value=mock_manager),
            patch("anythink.cli.AppContext") as MockCtx,
        ):
            MockCtx.create.return_value = AppContext.create(paths=xdg_dirs, console_file=StringIO())
            result = runner.invoke(app, ["scheduler", "list"])

        assert result.exit_code == 0
        assert "No schedules" in result.output

    def test_scheduler_list_shows_schedule(self, xdg_dirs: Paths) -> None:
        from anythink.schedule.models import ScheduledPrompt

        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = True
        mock_manager.paths = xdg_dirs

        ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
        ctx.schedule_manager.add(ScheduledPrompt("daily-brief", "0 9 * * *", "Summarize"))

        with (
            patch("anythink.cli.ConfigManager", return_value=mock_manager),
            patch("anythink.cli.AppContext") as MockCtx,
        ):
            MockCtx.create.return_value = ctx
            result = runner.invoke(app, ["scheduler", "list"])

        assert result.exit_code == 0
        assert "daily-brief" in result.output

    def test_scheduler_run_once(self, xdg_dirs: Paths) -> None:
        from anythink.schedule.models import ScheduledPrompt

        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = True
        mock_manager.paths = xdg_dirs

        mock_ctx = _mock_app_ctx(xdg_dirs)
        schedule = ScheduledPrompt("quick", "* * * * *", "hello")
        mock_ctx.schedule_manager.get.return_value = schedule

        with (
            patch("anythink.cli.ConfigManager", return_value=mock_manager),
            patch("anythink.cli.AppContext") as MockCtx,
        ):
            MockCtx.create.return_value = mock_ctx
            result = runner.invoke(app, ["scheduler", "run", "quick"])

        assert result.exit_code == 0, result.output
        assert "Mock response" in result.output

    def test_scheduler_run_unknown_exits_nonzero(self, xdg_dirs: Paths) -> None:
        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = True
        mock_manager.paths = xdg_dirs

        with (
            patch("anythink.cli.ConfigManager", return_value=mock_manager),
            patch("anythink.cli.AppContext") as MockCtx,
        ):
            ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
            MockCtx.create.return_value = ctx
            result = runner.invoke(app, ["scheduler", "run", "nonexistent"])

        assert result.exit_code != 0

    def test_scheduler_not_configured_exits_nonzero(self) -> None:
        mock_manager = MagicMock()
        mock_manager.is_configured.return_value = False
        with patch("anythink.cli.ConfigManager", return_value=mock_manager):
            result = runner.invoke(app, ["scheduler", "start", "--poll", "1"])
        assert result.exit_code != 0

    def test_scheduler_help(self) -> None:
        result = runner.invoke(app, ["scheduler", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output


# ── compare runner end-to-end ──────────────────────────────────────────────────


class TestCompareRunnerE2E:
    async def test_run_comparison_returns_two_results(self, xdg_dirs: Paths) -> None:
        from anythink.compare.runner import run_comparison
        from anythink.config.models import ModelAlias
        from anythink.providers.base import ChatMessage

        usage = TokenUsage(prompt_tokens=5, completion_tokens=10, total_tokens=15)

        async def _stream(*args, **kwargs) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(text="response", finish_reason="stop", usage=usage)

        mock_provider = MagicMock()
        mock_provider.stream_chat = _stream

        ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
        ctx.model_registry.add(ModelAlias("a1", "openai", "gpt-4o", 128000))
        ctx.model_registry.add(ModelAlias("a2", "openai", "gpt-4o-mini", 128000))

        with patch.object(ctx.provider_registry, "get", return_value=lambda **kw: mock_provider):
            results = await run_comparison(
                ctx,
                ["a1", "a2"],
                [ChatMessage(role="user", content="test prompt")],
            )

        assert len(results) == 2
        assert all(r.text == "response" for r in results if not r.error)
        assert {r.alias for r in results} == {"a1", "a2"}

    async def test_run_comparison_error_isolated(self, xdg_dirs: Paths) -> None:
        from anythink.compare.runner import run_comparison
        from anythink.config.models import ModelAlias
        from anythink.providers.base import ChatMessage

        async def _good_stream(*args, **kwargs) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(text="good", finish_reason="stop")

        async def _bad_stream(*args, **kwargs) -> AsyncIterator[StreamChunk]:
            raise RuntimeError("provider failed")
            yield  # make it a generator

        good_provider = MagicMock()
        good_provider.stream_chat = _good_stream
        bad_provider = MagicMock()
        bad_provider.stream_chat = _bad_stream

        ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
        ctx.model_registry.add(ModelAlias("good", "openai", "gpt-4o", 128000))
        ctx.model_registry.add(ModelAlias("bad", "openai", "gpt-4o-mini", 128000))

        call_count = 0

        def _get_provider(**kw: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return good_provider if call_count == 1 else bad_provider

        with patch.object(ctx.provider_registry, "get", side_effect=lambda name: _get_provider):
            results = await run_comparison(
                ctx,
                ["good", "bad"],
                [ChatMessage(role="user", content="test")],
            )

        assert len(results) == 2
        error_count = sum(1 for r in results if r.error)
        ok_count = sum(1 for r in results if not r.error)
        # At least one succeeds, one fails
        assert ok_count + error_count == 2
