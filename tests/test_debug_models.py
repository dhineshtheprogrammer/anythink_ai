"""Tests for debug data models (V3.2.0)."""

from __future__ import annotations

import time

import pytest

from anythink.debug.models import (
    HttpLogEntry,
    PluginEvent,
    RequestDebugRecord,
    TokenEntry,
    ToolCallEntry,
)


def _make_record(**kwargs) -> RequestDebugRecord:
    defaults = dict(
        request_id=1,
        session_id="sess-1",
        timestamp=__import__("datetime").datetime.utcnow(),
        model_id="test-model",
        provider_name="test-provider",
        alias_name="test",
        prompt_payload=[],
        gen_params=None,
    )
    defaults.update(kwargs)
    return RequestDebugRecord(**defaults)


def test_ttft_ms_none_when_no_first_token():
    rec = _make_record(t_api_sent=1.0, t_first_token=None)
    assert rec.ttft_ms() is None


def test_ttft_ms_calculated():
    t0 = time.monotonic()
    rec = _make_record(t_api_sent=t0, t_first_token=t0 + 0.150)
    assert 140.0 < rec.ttft_ms() < 160.0  # type: ignore[operator]


def test_stream_duration_ms_zero_when_incomplete():
    rec = _make_record(t_first_token=None, t_stream_end=0.0)
    assert rec.stream_duration_ms() == 0.0


def test_stream_duration_ms_calculated():
    t0 = time.monotonic()
    rec = _make_record(t_first_token=t0, t_stream_end=t0 + 0.742)
    assert 730.0 < rec.stream_duration_ms() < 750.0


def test_total_wall_ms_zero_when_render_not_complete():
    rec = _make_record(t_start=1.0, t_render_end=0.0)
    assert rec.total_wall_ms() == 0.0


def test_total_wall_ms_calculated():
    t0 = time.monotonic()
    rec = _make_record(t_start=t0, t_render_end=t0 + 1.577)
    assert 1560.0 < rec.total_wall_ms() < 1590.0


def test_rag_duration_ms_none_when_no_rag():
    rec = _make_record(t_rag_start=None, t_rag_end=None)
    assert rec.rag_duration_ms() is None


def test_rag_duration_ms_calculated():
    t0 = time.monotonic()
    rec = _make_record(t_rag_start=t0, t_rag_end=t0 + 0.082)
    assert 75.0 < rec.rag_duration_ms() < 90.0  # type: ignore[operator]


def test_search_duration_ms_none_when_no_search():
    rec = _make_record(t_search_start=None, t_search_end=None)
    assert rec.search_duration_ms() is None


def test_search_duration_ms_calculated():
    t0 = time.monotonic()
    rec = _make_record(t_search_start=t0, t_search_end=t0 + 0.340)
    assert 330.0 < rec.search_duration_ms() < 350.0  # type: ignore[operator]


def test_prompt_assembly_ms_zero_when_not_set():
    rec = _make_record(t_start=0.0, t_prompt_assembled=0.0)
    assert rec.prompt_assembly_ms() == 0.0


def test_prompt_assembly_ms_calculated():
    t0 = time.monotonic()
    rec = _make_record(t_start=t0, t_prompt_assembled=t0 + 0.014)
    assert 10.0 < rec.prompt_assembly_ms() < 20.0


def test_tool_call_entry_defaults():
    tc = ToolCallEntry(
        name="web_search",
        arguments={"query": "BERT"},
        result_summary="5 results",
        duration_s=0.34,
        success=True,
    )
    assert tc.used_in_response is False
    assert tc.success is True


def test_token_entry():
    t = TokenEntry(index=5, text=" hello", delta_ms=12.3)
    assert t.index == 5
    assert t.delta_ms == pytest.approx(12.3)


def test_plugin_event():
    ev = PluginEvent(
        plugin_name="my-plugin",
        hook_name="on_before_request",
        duration_ms=2.1,
        modified=False,
    )
    assert ev.modified is False


def test_http_log_entry():
    entry = HttpLogEntry(
        method="POST",
        url="https://api.anthropic.com/v1/messages",
        status_code=200,
        request_headers={"Authorization": "Bearer sk-...***"},
        request_body_snippet='{"model": "claude"}',
        response_headers={"content-type": "application/json"},
        round_trip_ms=210.5,
    )
    assert entry.status_code == 200
    assert "Bearer" in entry.request_headers["Authorization"]


def test_record_default_fields():
    rec = _make_record()
    assert rec.stop_reason is None
    assert rec.usage is None
    assert rec.completion_tokens == 0
    assert rec.tokens_per_second is None
    assert rec.was_stopped_by_user is False
    assert rec.rag_query == ""
    assert rec.rag_results == []
    assert rec.tool_calls == []
    assert rec.plugin_events == []
    assert rec.http_log is None
    assert rec.token_trace == []
    assert rec.agent_thinking == ""
