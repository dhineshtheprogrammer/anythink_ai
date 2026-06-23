"""Tests for /debug command handlers (V3.2.0)."""

from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from anythink.commands.base import CommandResult
from anythink.debug.commands import _debug_handler, _DEBUG_HELP_TABLE
from anythink.debug.manager import DebugManager
from anythink.debug.models import RequestDebugRecord


def _make_ctx(dm: DebugManager | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.debug_manager = dm if dm is not None else DebugManager()
    return ctx


def _make_state() -> MagicMock:
    state = MagicMock()
    state.model_id = "claude"
    state.history = []
    state.context_window = 8000
    state.session_id = "sess-1"
    state.provider = MagicMock()
    state.provider.name = "anthropic"
    state.gen_params = None
    return state


def _make_record(request_id: int = 1) -> RequestDebugRecord:
    t0 = time.monotonic()
    return RequestDebugRecord(
        request_id=request_id,
        session_id="sess",
        timestamp=datetime.utcnow(),
        model_id="test",
        provider_name="test",
        alias_name="test",
        prompt_payload=[{"role": "user", "content": "hello"}],
        gen_params=None,
        t_start=t0,
        t_prompt_assembled=t0 + 0.01,
        t_api_sent=t0 + 0.01,
        t_first_token=t0 + 0.2,
        t_stream_end=t0 + 1.0,
        t_render_end=t0 + 1.02,
        stop_reason="end_turn",
        completion_tokens=50,
        tokens_per_second=66.0,
    )


@pytest.mark.asyncio
async def test_debug_on():
    dm = DebugManager()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "on", _make_state(), MagicMock())
    assert result.action == "debug_hud_update"
    assert dm.is_active() is True
    assert "ON" in result.message


@pytest.mark.asyncio
async def test_debug_off():
    dm = DebugManager()
    dm.enable()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "off", _make_state(), MagicMock())
    assert result.action == "debug_hud_update"
    assert dm.is_active() is False
    assert "OFF" in result.message


@pytest.mark.asyncio
async def test_debug_toggle_on_then_off():
    dm = DebugManager()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "toggle", _make_state(), MagicMock())
    assert dm.is_active() is True
    result2 = await _debug_handler(ctx, "toggle", _make_state(), MagicMock())
    assert dm.is_active() is False


@pytest.mark.asyncio
async def test_debug_level():
    dm = DebugManager()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "level 3", _make_state(), MagicMock())
    assert dm.level() == 3
    assert result.action == "debug_hud_update"


@pytest.mark.asyncio
async def test_debug_level_invalid():
    dm = DebugManager()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "level abc", _make_state(), MagicMock())
    assert result.error is True


@pytest.mark.asyncio
async def test_debug_level_no_arg_shows_current():
    dm = DebugManager()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "level", _make_state(), MagicMock())
    assert result.error is True
    assert "Current debug level" in result.message


@pytest.mark.asyncio
async def test_debug_panel_toggle():
    dm = DebugManager()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "panel", _make_state(), MagicMock())
    assert result.action == "debug_panel_toggle"
    # The command handler only signals the TUI — it does NOT toggle panel state itself.
    # The actual toggle happens in AnythinkApp._toggle_debug_panel().
    assert dm.panel_open() is False  # state unchanged by command handler


@pytest.mark.asyncio
async def test_debug_api_toggle():
    dm = DebugManager()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "api", _make_state(), MagicMock())
    assert dm.api_logging_active() is True
    assert "ON" in result.message


@pytest.mark.asyncio
async def test_inspection_requires_debug_mode():
    dm = DebugManager()
    ctx = _make_ctx(dm)
    for sub in ["prompt", "timing", "stopreason", "tokens", "perf"]:
        result = await _debug_handler(ctx, sub, _make_state(), MagicMock())
        assert result.error is True
        assert "not active" in result.message


@pytest.mark.asyncio
async def test_debug_prompt_no_records():
    dm = DebugManager()
    dm.enable()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "prompt", _make_state(), MagicMock())
    assert result.error is True
    assert "No debug records" in result.message


@pytest.mark.asyncio
async def test_debug_prompt_with_record():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record())
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "prompt", _make_state(), MagicMock())
    assert result.error is False
    assert result.action == "debug_display"
    assert "claude" in result.message or "test" in result.message


@pytest.mark.asyncio
async def test_debug_timing_with_record():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record())
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "timing", _make_state(), MagicMock())
    assert result.error is False
    assert "Prompt assembly" in result.message


@pytest.mark.asyncio
async def test_debug_stopreason_with_record():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record())
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "stopreason", _make_state(), MagicMock())
    assert "end_turn" in result.message


@pytest.mark.asyncio
async def test_debug_tps_with_record():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record())
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "tps", _make_state(), MagicMock())
    assert "66" in result.message or "tok/s" in result.message


@pytest.mark.asyncio
async def test_debug_tokens_no_trace():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record())
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "tokens", _make_state(), MagicMock())
    # token_trace is empty by default — should report that
    assert "empty" in result.message.lower() or "level 3" in result.message.lower()


@pytest.mark.asyncio
async def test_debug_perf_with_records():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record(1))
    dm.finalize_request(_make_record(2))
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "perf", _make_state(), MagicMock())
    assert result.error is False
    assert "2 requests" in result.message


@pytest.mark.asyncio
async def test_debug_export(tmp_path):
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record(1))
    ctx = _make_ctx(dm)
    ctx.paths.debug_exports_dir = tmp_path
    result = await _debug_handler(ctx, "export", _make_state(), MagicMock())
    assert result.error is False
    assert "exported" in result.message


@pytest.mark.asyncio
async def test_debug_unknown_subcommand():
    dm = DebugManager()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "foobar", _make_state(), MagicMock())
    assert result.error is True
    assert "Unknown" in result.message


@pytest.mark.asyncio
async def test_debug_help_table_non_empty():
    assert len(_DEBUG_HELP_TABLE) > 10
    assert "on / off / toggle" in _DEBUG_HELP_TABLE


@pytest.mark.asyncio
async def test_debug_context_no_records():
    dm = DebugManager()
    dm.enable()
    ctx = _make_ctx(dm)
    # Context uses latest record (may be None) but still renders
    result = await _debug_handler(ctx, "context", _make_state(), MagicMock())
    assert result.action == "debug_display"
    assert result.error is False


@pytest.mark.asyncio
async def test_debug_diff_needs_two_records():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record(1))
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "diff", _make_state(), MagicMock())
    assert result.error is True
    assert "2" in result.message


@pytest.mark.asyncio
async def test_debug_diff_two_records():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record(1))
    dm.finalize_request(_make_record(2))
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "diff", _make_state(), MagicMock())
    assert result.action == "debug_display"


@pytest.mark.asyncio
async def test_debug_latency_no_records():
    dm = DebugManager()
    dm.enable()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "latency", _make_state(), MagicMock())
    assert result.error is True


@pytest.mark.asyncio
async def test_debug_latency_with_records():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record(1))
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "latency", _make_state(), MagicMock())
    assert result.error is False
    assert result.action == "debug_display"


@pytest.mark.asyncio
async def test_debug_replay_no_records():
    dm = DebugManager()
    dm.enable()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "replay", _make_state(), MagicMock())
    assert result.error is True


@pytest.mark.asyncio
async def test_debug_replay_latest():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record(1))
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "replay", _make_state(), MagicMock())
    assert result.action == "replay_stream"
    assert result.extra["record_id"] == 1
    assert result.extra["provider_alias"] is None


@pytest.mark.asyncio
async def test_debug_replay_with_provider():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record(1))
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "replay 1 --provider groq", _make_state(), MagicMock())
    assert result.action == "replay_stream"
    assert result.extra["provider_alias"] == "groq"


# ── V4 MMOS debug subcommands ─────────────────────────────────────────────────


def _make_record_with_routing(request_id: int = 1) -> RequestDebugRecord:
    """Create a debug record pre-populated with MMOS routing data."""
    from anythink.optimize.models import RoutingDecision

    rec = _make_record(request_id)
    rec.routing_decision = RoutingDecision(
        strategy="ensemble",
        primary_model="groq/llama3-70b",
        phase_models=["groq/llama3-70b", "ollama/mistral"],
        plan_mode=False,
        confidence=0.9,
        reason="Multi-model quality query",
    )
    rec.rate_limit_events = [{"model": "groq/llama3-70b", "event": "rpm_limit_hit"}]
    return rec


@pytest.mark.asyncio
async def test_debug_routing_no_records():
    dm = DebugManager()
    dm.enable()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "routing", _make_state(), MagicMock())
    assert result.error is True
    assert "No debug records" in result.message


@pytest.mark.asyncio
async def test_debug_routing_no_mmos_data():
    dm = DebugManager()
    dm.enable()
    rec = _make_record(1)
    # No routing_decision on record
    dm.finalize_request(rec)
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "routing", _make_state(), MagicMock())
    assert result.error is False
    assert "No MMOS routing decision" in result.message


@pytest.mark.asyncio
async def test_debug_routing_shows_strategy_and_model():
    dm = DebugManager()
    dm.enable()
    rec = _make_record_with_routing(1)
    dm.finalize_request(rec)
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "routing", _make_state(), MagicMock())
    assert result.error is False
    assert result.action == "debug_display"
    assert "ensemble" in result.message
    assert "groq/llama3-70b" in result.message
    assert "0.90" in result.message


@pytest.mark.asyncio
async def test_debug_plan_no_records():
    dm = DebugManager()
    dm.enable()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "plan", _make_state(), MagicMock())
    assert result.error is True


@pytest.mark.asyncio
async def test_debug_plan_no_plan_trace():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record(1))
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "plan", _make_state(), MagicMock())
    assert result.error is False
    assert "No Plan Mode trace" in result.message


@pytest.mark.asyncio
async def test_debug_plan_shows_plan_info():
    from datetime import datetime

    from anythink.optimize.plan import ExecutionPlan, PlanPhase, PLAN_STATUS_DONE

    dm = DebugManager()
    dm.enable()
    rec = _make_record(1)
    plan = ExecutionPlan(
        plan_id="test-plan-id",
        session_id="sess",
        original_query="Build a React app with Node.js backend",
        phases=[
            PlanPhase(
                phase_num=1,
                title="Project structure",
                description="Set up folders",
                model_id="groq/llama3-70b",
                estimated_tokens=800,
                status=PLAN_STATUS_DONE,
                output="Here is the structure...",
                elapsed_s=3.2,
                actual_model="groq/llama3-70b",
            )
        ],
        created_at=datetime.utcnow(),
        recombination_model="ollama/mistral",
        status=PLAN_STATUS_DONE,
        final_output="Final synthesised answer.",
    )
    rec.plan_trace = plan
    dm.finalize_request(rec)
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "plan", _make_state(), MagicMock())
    assert result.error is False
    assert result.action == "debug_display"
    assert "test-plan-id" in result.message
    assert "Build a React app" in result.message
    assert "done" in result.message.lower()


@pytest.mark.asyncio
async def test_debug_ratelimit_no_records():
    dm = DebugManager()
    dm.enable()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "ratelimit", _make_state(), MagicMock())
    assert result.error is True


@pytest.mark.asyncio
async def test_debug_ratelimit_no_events():
    dm = DebugManager()
    dm.enable()
    dm.finalize_request(_make_record(1))
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "ratelimit", _make_state(), MagicMock())
    assert result.error is False
    assert "No rate limit events" in result.message


@pytest.mark.asyncio
async def test_debug_ratelimit_shows_events():
    dm = DebugManager()
    dm.enable()
    rec = _make_record_with_routing(1)
    dm.finalize_request(rec)
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "ratelimit", _make_state(), MagicMock())
    assert result.error is False
    assert result.action == "debug_display"
    assert "rpm_limit_hit" in result.message


@pytest.mark.asyncio
async def test_debug_help_includes_v4_commands():
    dm = DebugManager()
    ctx = _make_ctx(dm)
    result = await _debug_handler(ctx, "help", _make_state(), MagicMock())
    assert "routing" in result.message
    assert "plan" in result.message
    assert "ratelimit" in result.message
