"""Rich Text formatters for debug inspection output (V3.2.0).

All functions are pure: they accept data objects and return formatted
strings (or Rich Text). No TUI coupling.
"""

from __future__ import annotations

import difflib
import json
import textwrap
from typing import TYPE_CHECKING, Any

from anythink.ui.icons import VS15

if TYPE_CHECKING:
    from anythink.debug.models import RequestDebugRecord


# ── helpers ───────────────────────────────────────────────────────────────────


def _box(title: str, lines: list[str], width: int = 68) -> str:
    inner = width - 4
    top = f"╭─ {title} {'─' * max(0, inner - len(title) - 1)}╮"
    bottom = "╰" + "─" * (width - 2) + "╯"
    body = "\n".join(f"│  {line:<{inner}}│" for line in lines)
    return f"{top}\n{body}\n{bottom}"


def _ms(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.0f}ms"


# ── format_prompt_payload ─────────────────────────────────────────────────────


def format_prompt_payload(record: RequestDebugRecord) -> str:
    """Render the full prompt payload in a readable format."""
    lines: list[str] = [
        f"Model:       {record.model_id}",
        f"Provider:    {record.provider_name}",
        f"Request #:   {record.request_id}",
        "",
    ]
    if record.gen_params:
        gp = record.gen_params
        lines.append(
            f"Params:  temp={gp.temperature}"
            + (f"  max_tokens={gp.max_tokens}" if gp.max_tokens else "")
            + (f"  top_p={gp.top_p}" if gp.top_p else "")
        )
        lines.append("")

    for i, msg in enumerate(record.prompt_payload):
        role = msg.get("role", "?").upper()
        content = msg.get("content", "")
        if isinstance(content, list):
            text_content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        else:
            text_content = str(content)
        lines.append(f"── TURN {i + 1} · {role} " + "─" * max(0, 40 - len(role)))
        for chunk in textwrap.wrap(text_content, width=60) or [text_content[:60]]:
            lines.append(f"  {chunk}")
        lines.append("")

    return _box(f"🔬 Raw Prompt Payload — Request #{record.request_id}", lines)


# ── format_timing_breakdown ───────────────────────────────────────────────────


def format_timing_breakdown(record: RequestDebugRecord) -> str:
    """Render the per-stage latency breakdown table."""
    rows: list[tuple[str, str, str]] = []

    def _add(label: str, duration: float | None, cumul: float) -> float:
        if duration is None:
            return cumul
        rows.append((label, _ms(duration), _ms(cumul + duration)))
        return cumul + duration

    cumul = 0.0
    cumul = _add("Prompt assembly", record.prompt_assembly_ms(), cumul)
    cumul = _add("RAG retrieval", record.rag_duration_ms(), cumul)
    cumul = _add("Web search", record.search_duration_ms(), cumul)
    cumul = _add("API call (queue + network)", record.api_overhead_ms() or None, cumul)
    if record.ttft_ms() is not None:
        _ttft = record.ttft_ms()
        rows.append(("Time to first token (TTFT)", _ms(_ttft), _ms(cumul + _ttft)))  # type: ignore[operator]
        cumul += _ttft  # type: ignore[operator]
    cumul = _add("Token stream duration", record.stream_duration_ms() or None, cumul)
    if record.t_render_end and record.t_stream_end:
        render_ms = (record.t_render_end - record.t_stream_end) * 1000
        cumul = _add("Response rendering", render_ms, cumul)

    col_w = 36
    lines: list[str] = [
        f"{'Stage':<{col_w}} {'Duration':>10}  {'Cumulative':>12}",
        "─" * 62,
    ]
    for stage, dur, cum in rows:
        lines.append(f"{stage:<{col_w}} {dur:>10}  {cum:>12}")
    lines.append("─" * 62)
    lines.append(f"{'Total wall time':<{col_w}} {_ms(record.total_wall_ms()):>10}")
    lines.append("")
    if record.provider_name:
        lines.append(f"Provider: {record.provider_name}")

    return _box(f"🔬 Request Timing — Request #{record.request_id}", lines)


# ── format_stop_reason ────────────────────────────────────────────────────────

_STOP_DESCRIPTIONS: dict[str, str] = {
    "end_turn": "Model naturally completed its response",
    "max_tokens": "Response was cut off at the token limit",
    "stop_sequence": "A configured stop string halted generation",
    "tool_use": "Model paused to call a tool",
    "cancelled": "Generation was stopped by the user",
    "error": "Generation ended due to a provider-side error",
    "timeout": "Generation halted due to a connection timeout",
    "length": "Response was cut off at the token limit",
    "stop": "Model naturally completed its response",
}


def format_stop_reason(record: RequestDebugRecord) -> str:
    reason = record.stop_reason or "unknown"
    desc = _STOP_DESCRIPTIONS.get(reason, "Unknown stop condition")
    lines = [
        f"Stop reason:  {reason}",
        f"Meaning:      {desc}",
    ]
    if reason in ("max_tokens", "length"):
        lines += [
            "",
            f"⚠{VS15}  The response was silently truncated.",
            "   Consider increasing max_tokens for this alias.",
        ]
    return _box(f"🔬 Stop Reason — Request #{record.request_id}", lines)


# ── format_token_trace ────────────────────────────────────────────────────────


def format_token_trace(record: RequestDebugRecord) -> str:
    if not record.token_trace:
        return "Token trace is empty. Enable Level 3 before sending a message:\n" "  /debug level 3"
    avg_delta = sum(t.delta_ms for t in record.token_trace) / len(record.token_trace)
    threshold = avg_delta * 3

    lines: list[str] = []
    for entry in record.token_trace[:80]:  # cap display at 80 tokens
        flag = " ← long pause" if entry.delta_ms > threshold and entry.index > 0 else ""
        tok_repr = repr(entry.text)[:16]
        lines.append(f"  #{entry.index:<4} {tok_repr:<18} +{entry.delta_ms:.0f}ms{flag}")

    if len(record.token_trace) > 80:
        lines.append(f"  … ({len(record.token_trace) - 80} more tokens not shown)")

    lines.append("")
    lines.append(
        f"▸ {len(record.token_trace)} tokens  "
        f"avg {avg_delta:.0f}ms/token  "
        f"total stream {record.stream_duration_ms():.0f}ms"
    )
    return _box(f"🔬 Token Stream Trace — Request #{record.request_id}", lines)


# ── format_context_window ─────────────────────────────────────────────────────


def format_context_window(state: Any, record: RequestDebugRecord | None) -> str:
    """Render the context window composition breakdown."""

    def _tok(text: str) -> int:
        return max(1, len(text) // 4)

    rows: list[tuple[str, int]] = []
    total = 0

    for item in (record.prompt_payload if record else []):
        role = item.get("role", "?")
        content = item.get("content", "")
        if isinstance(content, list):
            text = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        else:
            text = str(content)
        t = _tok(text)
        rows.append((f"Turn · {role}", t))
        total += t

    ctx_max = getattr(state, "context_window", 0)
    pct = (total / ctx_max * 100) if ctx_max > 0 else 0.0
    bar_filled = int(pct / 100 * 30)
    bar = "█" * bar_filled + "░" * (30 - bar_filled)

    lines: list[str] = [
        f"{'Component':<40} {'Tokens':>8}  {'%':>6}",
        "─" * 58,
    ]
    for label, tok in rows:
        p = f"{tok / ctx_max * 100:.2f}%" if ctx_max else "—"
        lines.append(f"{label:<40} {tok:>8,}  {p:>6}")
    lines.append("─" * 58)
    lines.append(f"{'Total used':<40} {total:>8,}  {pct:>5.2f}%")
    if ctx_max:
        lines.append(f"{'Remaining':<40} {ctx_max - total:>8,}  {100 - pct:>5.2f}%")
    lines.append("")
    lines.append(f"{bar}  {pct:.2f}%")

    return _box(f"🔬 Context Window — {getattr(state, 'model_id', 'unknown')}", lines)


# ── format_latency_chart ──────────────────────────────────────────────────────


def format_latency_chart(records: list[RequestDebugRecord], width: int = 60) -> str:
    """Render an ASCII line chart of total wall time across requests."""
    if not records:
        return "No records."

    values = [r.total_wall_ms() for r in records]
    max_v = max(values) if max(values) > 0 else 1
    chart_h = 6
    chart_w = min(width - 8, len(values) * 5)

    rows_ms = [max_v * (chart_h - i) / chart_h for i in range(chart_h + 1)]
    grid = [[" "] * chart_w for _ in range(chart_h + 1)]

    for col, val in enumerate(values):
        x = int(col / len(values) * chart_w)
        y = chart_h - int(val / max_v * chart_h)
        if 0 <= x < chart_w and 0 <= y <= chart_h:
            grid[y][x] = "●"

    lines: list[str] = ["ms"]
    for row_idx, row in enumerate(grid):
        label = f"{rows_ms[row_idx]:>6.0f} │"
        lines.append(label + "".join(row))
    lines.append(" " * 7 + "┴" + "─" * chart_w)
    labels = "  ".join(f"#{r.request_id}" for r in records)
    lines.append(" " * 8 + labels[:chart_w])
    lines.append("")

    if values:
        avg = sum(values) / len(values)
        lines.append(
            f"Avg: {avg:.0f}ms   "
            f"Min: {min(values):.0f}ms (#{records[values.index(min(values))].request_id})   "
            f"Max: {max(values):.0f}ms (#{records[values.index(max(values))].request_id})"
        )

    return _box("🔬 Latency History — Current Session", lines)


# ── format_perf_summary ───────────────────────────────────────────────────────


def format_perf_summary(records: list[RequestDebugRecord]) -> str:
    """Render a comprehensive session performance report."""
    if not records:
        return "No debug records."

    walls = [r.total_wall_ms() for r in records if r.total_wall_ms() > 0]
    ttfts = [r.ttft_ms() for r in records if r.ttft_ms() is not None]
    tpss = [r.tokens_per_second for r in records if r.tokens_per_second]
    prompt_toks = sum(r.usage.prompt_tokens for r in records if r.usage)
    comp_toks = sum(r.usage.completion_tokens for r in records if r.usage)

    lines: list[str] = [f"{len(records)} requests recorded", ""]

    lines.append("Response Time")
    lines.append("─" * 50)
    if ttfts:
        lines.append(f"Average TTFT        {sum(ttfts)/len(ttfts):.0f}ms")
        min_ttft = min(ttfts)
        max_ttft = max(ttfts)
        lines.append(f"Fastest TTFT        {min_ttft:.0f}ms")
        lines.append(f"Slowest TTFT        {max_ttft:.0f}ms")
    if walls:
        lines.append(f"Average total time  {sum(walls)/len(walls):.0f}ms")
        lines.append(f"Slowest request     {max(walls):.0f}ms")
    lines.append("")

    if tpss:
        lines.append("Generation Speed")
        lines.append("─" * 50)
        lines.append(f"Average tok/s       {sum(tpss)/len(tpss):.0f} tok/s")
        lines.append(f"Fastest             {max(tpss):.0f} tok/s")
        lines.append(f"Slowest             {min(tpss):.0f} tok/s")
        lines.append("")

    lines.append("Token Usage")
    lines.append("─" * 50)
    lines.append(f"Total prompt tokens     {prompt_toks:,}")
    lines.append(f"Total completion tokens {comp_toks:,}")
    lines.append(f"Total tokens            {prompt_toks + comp_toks:,}")

    tool_calls_total = sum(len(r.tool_calls) for r in records)
    if tool_calls_total:
        lines.append("")
        lines.append("Tool Usage")
        lines.append("─" * 50)
        lines.append(f"Total tool calls    {tool_calls_total}")
        successes = sum(1 for r in records for tc in r.tool_calls if tc.success)
        lines.append(f"Success rate        {successes}/{tool_calls_total}")

    return _box("🔬 Session Performance Summary", lines)


# ── format_rag_chunks ─────────────────────────────────────────────────────────


def format_rag_chunks(record: RequestDebugRecord) -> str:
    """Render the RAG chunk inspector (injected + rejected)."""
    if not record.rag_results:
        return "No RAG retrieval data for the last request."

    threshold = 0.70
    injected = [r for r in record.rag_results if r.relevance >= threshold]
    rejected = [r for r in record.rag_results if r.relevance < threshold]

    lines: list[str] = [
        f"Query:  {record.rag_query[:60]}",
        f"Threshold: {threshold:.0%}   Injected: {len(injected)}   Rejected: {len(rejected)}",
        "",
        "INJECTED (above threshold)",
        "─" * 56,
    ]
    for i, r in enumerate(injected, 1):
        lines.append(f"✓ #{i}  {r.source_path[:30]:<30}  Score: {r.relevance:.0%}")
        lines.append(f"     {r.excerpt(60)}")
        lines.append("")

    if rejected:
        lines.append("REJECTED (below threshold)")
        lines.append("─" * 56)
        for i, r in enumerate(rejected, len(injected) + 1):
            lines.append(f"✕ #{i}  {r.source_path[:30]:<30}  Score: {r.relevance:.0%}")
            lines.append(f"     {r.excerpt(60)}")
            lines.append("")

    lines.append("Adjust threshold: /rag threshold <value>")
    return _box(f'🔬 RAG Chunk Inspector — Query: "{record.rag_query[:30]}"', lines)


# ── format_embeddings ─────────────────────────────────────────────────────────


def format_embeddings(record: RequestDebugRecord) -> str:
    """Render the embedding inspector."""
    lines: list[str] = [
        f"Query embedded:  {record.rag_query[:60]}",
        "",
        f"Embedding time:  {_ms(record.rag_embedding_ms)}",
        f"Candidates evaluated: {record.rag_candidates_evaluated}",
        "Score threshold: 0.70",
        f"Chunks above threshold: {sum(1 for r in record.rag_results if r.relevance >= 0.70)}",
        f"Chunks injected: {min(5, sum(1 for r in record.rag_results if r.relevance >= 0.70))}",
    ]
    if not record.rag_query:
        lines = ["No RAG retrieval occurred for the last request."]
    return _box(f"🔬 Embedding Inspector — Request #{record.request_id}", lines)


# ── format_rag_inject ─────────────────────────────────────────────────────────


def format_rag_inject(record: RequestDebugRecord) -> str:
    """Show what was injected into context from RAG."""
    threshold = 0.70
    injected = [r for r in record.rag_results if r.relevance >= threshold]
    if not injected:
        return "No RAG content was injected for the last request."

    lines: list[str] = [
        f"[RAG PREAMBLE] Retrieved from index, threshold {threshold:.0%}:",
        "",
    ]
    for i, r in enumerate(injected[:5], 1):
        lines.append(f"  [CHUNK {i} · {r.source_path}")
        if r.start_line and r.end_line:
            lines[-1] += f" · lines {r.start_line}-{r.end_line}"
        lines[-1] += "]"
        for line in textwrap.wrap(r.chunk_text[:200], width=60):
            lines.append(f"  {line}")
        lines.append("")

    return _box(f"🔬 RAG Injection Preview — Request #{record.request_id}", lines)


# ── format_tool_trace ─────────────────────────────────────────────────────────


def format_tool_trace(record: RequestDebugRecord) -> str:
    """Render the tool call trace."""
    if not record.tool_calls:
        return "No tool calls were made in the last request."

    total_tool_time = sum(tc.duration_s for tc in record.tool_calls)
    lines: list[str] = []
    for i, tc in enumerate(record.tool_calls, 1):
        status = "✓ Success" if tc.success else "✕ Failed"
        used = "✓ Yes" if tc.used_in_response else "— Not referenced"
        lines += [
            f"Call #{i} · {tc.name}  ── {tc.duration_s * 1000:.0f}ms ──",
            f"Input:   {json.dumps(tc.arguments, ensure_ascii=False)[:60]}",
            f"Status:  {status}",
            f"Output:  {tc.result_summary[:60]}",
            f"Used:    {used}",
            "",
        ]
    lines += [
        f"Total tool calls: {len(record.tool_calls)}   "
        f"Total tool time: {total_tool_time * 1000:.0f}ms",
    ]
    if record.total_wall_ms():
        pct = total_tool_time * 1000 / record.total_wall_ms() * 100
        lines.append(f"Tool time as % of total: {pct:.1f}%")

    return _box(f"🔬 Tool Call Trace — Request #{record.request_id}", lines)


# ── format_agent_log ──────────────────────────────────────────────────────────


def format_agent_log(record: RequestDebugRecord) -> str:
    """Render the agent decision log / extended thinking."""
    if not record.agent_thinking:
        return (
            "Agent thinking not available for this provider or request.\n"
            "(Extended thinking is only available for select Anthropic models "
            "when enabled in generation parameters.)"
        )
    lines: list[str] = []
    for line in textwrap.wrap(record.agent_thinking, width=62):
        lines.append(line)
    return _box(f"🔬 Agent Decision Log — Request #{record.request_id}", lines)


# ── format_tool_diff ──────────────────────────────────────────────────────────


def format_tool_diff(a: RequestDebugRecord, b: RequestDebugRecord) -> str:
    """Diff tool outputs between two recorded requests."""

    def _summary(tc_list: list[Any]) -> list[str]:
        return [f"{tc.name}: {tc.result_summary[:80]}" for tc in tc_list]

    diff = list(
        difflib.unified_diff(
            _summary(a.tool_calls),
            _summary(b.tool_calls),
            fromfile=f"Request #{a.request_id}",
            tofile=f"Request #{b.request_id}",
            lineterm="",
        )
    )
    if not diff:
        return f"Tool outputs are identical between Request #{a.request_id} and #{b.request_id}."

    lines = diff[:60]
    return _box(
        f"🔬 Tool Output Diff — #{a.request_id} vs #{b.request_id}",
        lines,
    )


# ── format_prompt_diff ────────────────────────────────────────────────────────


def format_prompt_diff(a: RequestDebugRecord, b: RequestDebugRecord) -> str:
    """Render a unified diff between two prompt payloads."""

    def _flatten(payload: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        for item in payload:
            role = item.get("role", "?")
            content = item.get("content", "")
            if isinstance(content, list):
                text = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            else:
                text = str(content)
            lines.append(f"[{role}] {text[:120]}")
        return lines

    diff = list(
        difflib.unified_diff(
            _flatten(a.prompt_payload),
            _flatten(b.prompt_payload),
            fromfile=f"Request #{a.request_id}",
            tofile=f"Request #{b.request_id}",
            lineterm="",
        )
    )
    if not diff:
        return f"Prompts are identical between Request #{a.request_id} and #{b.request_id}."

    lines = diff[:60]
    return _box(f"🔬 Prompt Diff — #{a.request_id} vs #{b.request_id}", lines)


# ── format_plugin_trace ───────────────────────────────────────────────────────


def format_plugin_trace(record: RequestDebugRecord) -> str:
    """Render the plugin invocation trace."""
    if not record.plugin_events:
        return "No plugin events recorded for the last request."

    lines: list[str] = []
    current_plugin = ""
    for ev in record.plugin_events:
        if ev.plugin_name != current_plugin:
            current_plugin = ev.plugin_name
            lines.append(f"Plugin: {ev.plugin_name}")
            lines.append("")
        modified = "modified" if ev.modified else "passthrough"
        lines.append(f"  Hook: {ev.hook_name:<28} {ev.duration_ms:.1f}ms  [{modified}]")
    return _box(f"🔬 Plugin Trace — Request #{record.request_id}", lines)


# ── format_compare_table ──────────────────────────────────────────────────────


def format_compare_table(results: list[Any]) -> str:
    """Render a technical comparison table for /debug compare."""
    if not results:
        return "No comparison results."

    lines: list[str] = [
        f"{'Metric':<28}" + "  ".join(f"{r.alias:<16}" for r in results),
        "─" * (28 + 18 * len(results)),
    ]

    def _row(label: str, values: list[str]) -> str:
        return f"{label:<28}" + "  ".join(f"{v:<16}" for v in values)

    ttfts = [getattr(r, "ttft_ms", None) for r in results]
    lines.append(_row("TTFT", [_ms(v) if v else "—" for v in ttfts]))

    walls = [getattr(r, "wall_ms", None) for r in results]
    lines.append(_row("Total wall time", [_ms(v) if v else "—" for v in walls]))

    tpss = [getattr(r, "tokens_per_second", None) for r in results]
    lines.append(_row("Tokens/second", [f"{v:.0f}" if v else "—" for v in tpss]))

    stop_reasons = [getattr(r, "stop_reason", "—") or "—" for r in results]
    lines.append(_row("Stop reason", stop_reasons))

    return _box("🔬 Provider Debug Comparison", lines)


# ── format_validation_table ───────────────────────────────────────────────────


def format_validation_table(issues: list[Any]) -> str:
    """Render the /config validate results table."""
    if not issues:
        return "✓ All configuration checks passed."

    lines: list[str] = [
        f"{'Status':<6} {'Category':<18} {'Field':<22} Message",
        "─" * 70,
    ]
    for issue in issues:
        icon = {"ok": "✓", "warn": f"⚠{VS15}", "error": f"❌{VS15}"}.get(issue.severity, "?")
        lines.append(f"{icon:<6} {issue.category:<18} {issue.field:<22} {issue.message}")
        if issue.suggestion:
            lines.append(f"{'':6} {'':18} {'':22} → {issue.suggestion}")

    ok = sum(1 for i in issues if i.severity == "ok")
    warn = sum(1 for i in issues if i.severity == "warn")
    err = sum(1 for i in issues if i.severity == "error")
    lines.append("─" * 70)
    lines.append(f"✓ {ok}  ⚠{VS15} {warn}  ❌{VS15} {err}")

    return _box("🔬 Config Deep Validation", lines)
