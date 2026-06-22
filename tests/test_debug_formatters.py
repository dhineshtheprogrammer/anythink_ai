"""Tests for debug formatters (V3.2.0)."""

from __future__ import annotations

import time
from datetime import datetime

import pytest

from anythink.debug.formatters import (
    format_agent_log,
    format_context_window,
    format_embeddings,
    format_latency_chart,
    format_perf_summary,
    format_plugin_trace,
    format_prompt_diff,
    format_prompt_payload,
    format_rag_chunks,
    format_rag_inject,
    format_stop_reason,
    format_timing_breakdown,
    format_token_trace,
    format_tool_diff,
    format_tool_trace,
    format_validation_table,
)
from anythink.debug.models import (
    PluginEvent,
    RequestDebugRecord,
    TokenEntry,
    ToolCallEntry,
)


def _rec(**kwargs) -> RequestDebugRecord:
    t0 = time.monotonic()
    defaults = dict(
        request_id=1,
        session_id="sess",
        timestamp=datetime.utcnow(),
        model_id="claude-sonnet-4-6",
        provider_name="anthropic",
        alias_name="claude",
        prompt_payload=[
            {"role": "user", "content": "What is BERT?"},
            {"role": "assistant", "content": "BERT is a transformer model."},
        ],
        gen_params=None,
        t_start=t0,
        t_prompt_assembled=t0 + 0.014,
        t_api_sent=t0 + 0.100,
        t_first_token=t0 + 0.300,
        t_stream_end=t0 + 1.000,
        t_render_end=t0 + 1.020,
        stop_reason="end_turn",
        completion_tokens=83,
        tokens_per_second=111.0,
    )
    defaults.update(kwargs)
    return RequestDebugRecord(**defaults)


def test_format_prompt_payload_contains_model():
    out = format_prompt_payload(_rec())
    assert "claude-sonnet-4-6" in out
    assert "Request #1" in out
    assert "USER" in out


def test_format_prompt_payload_shows_turns():
    out = format_prompt_payload(_rec())
    assert "BERT" in out


def test_format_timing_breakdown_shows_stages():
    out = format_timing_breakdown(_rec())
    assert "Prompt assembly" in out
    assert "Total wall time" in out
    assert "Request #1" in out


def test_format_timing_breakdown_ttft():
    out = format_timing_breakdown(_rec())
    assert "TTFT" in out or "first token" in out.lower()


def test_format_stop_reason_end_turn():
    out = format_stop_reason(_rec(stop_reason="end_turn"))
    assert "end_turn" in out
    assert "naturally" in out.lower()


def test_format_stop_reason_max_tokens_warning():
    out = format_stop_reason(_rec(stop_reason="max_tokens"))
    assert "truncated" in out.lower()


def test_format_stop_reason_unknown():
    out = format_stop_reason(_rec(stop_reason=None))
    assert "unknown" in out


def test_format_token_trace_empty():
    out = format_token_trace(_rec(token_trace=[]))
    assert "empty" in out.lower() or "level 3" in out.lower()


def test_format_token_trace_with_data():
    tokens = [TokenEntry(i, f"tok{i}", float(10 + i)) for i in range(5)]
    out = format_token_trace(_rec(token_trace=tokens))
    assert "tok0" in out
    assert "5 tokens" in out


def test_format_context_window_basic():
    class FakeState:
        model_id = "test"
        context_window = 1000

    out = format_context_window(FakeState(), _rec())
    assert "user" in out.lower()
    assert "Total used" in out


def test_format_latency_chart_single():
    out = format_latency_chart([_rec()])
    assert "#1" in out
    assert "ms" in out or "Avg" in out


def test_format_latency_chart_multiple():
    records = [_rec(request_id=i) for i in range(1, 4)]
    out = format_latency_chart(records)
    assert "Avg" in out
    assert "Min" in out
    assert "Max" in out


def test_format_perf_summary_basic():
    from anythink.providers.base import TokenUsage

    rec = _rec(usage=TokenUsage(prompt_tokens=100, completion_tokens=83, total_tokens=183))
    out = format_perf_summary([rec])
    assert "requests recorded" in out
    assert "Token Usage" in out


def test_format_rag_chunks_no_results():
    out = format_rag_chunks(_rec(rag_results=[]))
    assert "No RAG" in out


def test_format_rag_chunks_with_results():
    from anythink.rag.models import RetrievalResult

    results = [
        RetrievalResult("src/main.py", "class Foo:", 0.94),
        RetrievalResult("docs/api.md", "## API", 0.55),
    ]
    out = format_rag_chunks(_rec(rag_results=results))
    assert "INJECTED" in out
    assert "REJECTED" in out
    assert "src/main.py" in out


def test_format_embeddings_no_rag():
    out = format_embeddings(_rec(rag_query="", rag_results=[]))
    assert "No RAG" in out or "embedded" in out.lower()


def test_format_embeddings_with_data():
    from anythink.rag.models import RetrievalResult

    rec = _rec(
        rag_query="BERT attention",
        rag_embedding_ms=34.0,
        rag_candidates_evaluated=1247,
        rag_results=[RetrievalResult("f.py", "code", 0.94)],
    )
    out = format_embeddings(rec)
    assert "1247" in out
    assert "34" in out


def test_format_rag_inject_no_results():
    out = format_rag_inject(_rec(rag_results=[]))
    assert "No RAG" in out


def test_format_rag_inject_with_results():
    from anythink.rag.models import RetrievalResult

    results = [RetrievalResult("src/main.py", "class Foo:\n    pass", 0.94)]
    out = format_rag_inject(_rec(rag_results=results))
    assert "CHUNK 1" in out
    assert "src/main.py" in out


def test_format_tool_trace_no_calls():
    out = format_tool_trace(_rec(tool_calls=[]))
    assert "No tool calls" in out


def test_format_tool_trace_with_calls():
    calls = [
        ToolCallEntry("web_search", {"query": "BERT"}, "5 results", 0.34, True),
        ToolCallEntry("code_exec", {"lang": "python"}, "0", 0.12, True, used_in_response=True),
    ]
    out = format_tool_trace(_rec(tool_calls=calls))
    assert "web_search" in out
    assert "Total tool calls: 2" in out


def test_format_agent_log_empty():
    out = format_agent_log(_rec(agent_thinking=""))
    assert "not available" in out.lower()


def test_format_agent_log_with_thinking():
    out = format_agent_log(_rec(agent_thinking="I should search for BERT papers."))
    assert "BERT" in out


def test_format_tool_diff_no_calls():
    a = _rec(request_id=1, tool_calls=[])
    b = _rec(request_id=2, tool_calls=[])
    out = format_tool_diff(a, b)
    assert "identical" in out.lower()


def test_format_tool_diff_with_diff():
    a = _rec(request_id=1, tool_calls=[ToolCallEntry("search", {}, "result A", 0.1, True)])
    b = _rec(request_id=2, tool_calls=[ToolCallEntry("search", {}, "result B", 0.1, True)])
    out = format_tool_diff(a, b)
    assert "#1" in out or "#2" in out


def test_format_prompt_diff_identical():
    rec = _rec()
    out = format_prompt_diff(rec, rec)
    assert "identical" in out.lower()


def test_format_prompt_diff_different():
    a = _rec(request_id=1, prompt_payload=[{"role": "user", "content": "Hello"}])
    b = _rec(request_id=2, prompt_payload=[{"role": "user", "content": "Goodbye"}])
    out = format_prompt_diff(a, b)
    assert "#1" in out
    assert "#2" in out


def test_format_plugin_trace_empty():
    out = format_plugin_trace(_rec(plugin_events=[]))
    assert "No plugin events" in out


def test_format_plugin_trace_with_events():
    events = [
        PluginEvent("my-plugin", "on_before_request", 2.0, False),
        PluginEvent("my-plugin", "on_response_complete", 1.0, True),
    ]
    out = format_plugin_trace(_rec(plugin_events=events))
    assert "my-plugin" in out
    assert "on_before_request" in out


def test_format_validation_table_empty():
    out = format_validation_table([])
    assert "passed" in out.lower()


def test_format_validation_table_with_issues():
    from anythink.config.validator import ValidationIssue

    issues = [
        ValidationIssue("Aliases", "alias:bad", "error", "Provider not found", "pip install x"),
        ValidationIssue("Theme", "active_theme", "ok", "Theme valid"),
    ]
    out = format_validation_table(issues)
    assert "❌" in out
    assert "✓" in out
    assert "Provider not found" in out
