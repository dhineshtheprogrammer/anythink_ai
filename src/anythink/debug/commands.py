"""Slash command handlers for the /debug namespace (V3.2.0)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anythink.commands.base import CommandResult, SlashCommand

if TYPE_CHECKING:
    from anythink.app.chat import ChatState
    from anythink.app.context import AppContext
    from anythink.commands.registry import CommandRegistry
    from anythink.debug.models import RequestDebugRecord


_DEBUG_HELP_TABLE: dict[str, str] = {
    "on / off / toggle": "Activate or deactivate debug mode",
    "level <1|2|3>": "Set verbosity level (1=minimal, 2=full, 3=max)",
    "panel": "Toggle live debug side panel",
    "prompt [n]": "Inspect raw payload of request n (or latest)",
    "timing [n]": "Per-stage latency breakdown",
    "stopreason": "Stop reason for the last response",
    "tokens": "Token-by-token stream trace (Level 3 only)",
    "tps": "Tokens per second for the last response",
    "context": "Context window composition breakdown",
    "diff [n1 n2]": "Prompt diff between two requests",
    "chunks": "RAG chunk inspector (injected + rejected)",
    "embeddings": "Embedding search process details",
    "raginject": "What RAG injected into context",
    "tools": "Tool call trace",
    "agent": "Agent decision log / extended thinking",
    "tooldiff [n1 n2]": "Diff tool outputs between two runs",
    "api": "Toggle raw HTTP request/response logging",
    "replay [n]": "Replay request n (or latest) to same provider",
    "replay [n] --provider <alias>": "Replay to a different provider",
    "latency": "ASCII latency history chart",
    "compare <alias...>": "Technical multi-provider comparison",
    "plugins": "Plugin invocation trace",
    "export": "Export debug log to JSON file",
    "export --format txt": "Export debug log to plain text",
    "perf": "Session performance summary",
    # V4 MMOS
    "routing": "Show MMOS routing decision for the last query",
    "plan": "Show full Plan Mode execution trace for the last run",
    "ratelimit": "Show rate limit event log",
}


async def _debug_handler(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Route /debug subcommands to their implementations."""
    parts = args.strip().split()
    sub = parts[0].lower() if parts else ""
    rest = parts[1:] if len(parts) > 1 else []
    rest_str = " ".join(rest)
    dm = ctx.debug_manager

    # ── mode control ──────────────────────────────────────────────────────
    if sub == "on":
        dm.enable(level=dm.level())
        return CommandResult(
            message=f"Debug mode ON (Level {dm.level()})",
            action="debug_hud_update",
        )

    if sub == "off":
        dm.disable()
        return CommandResult(message="Debug mode OFF", action="debug_hud_update")

    if sub in ("toggle", "") and not sub:
        new_state = dm.toggle()
        label = "ON" if new_state else "OFF"
        return CommandResult(message=f"Debug mode {label}", action="debug_hud_update")

    if sub == "toggle":
        new_state = dm.toggle()
        label = "ON" if new_state else "OFF"
        return CommandResult(message=f"Debug mode {label}", action="debug_hud_update")

    if sub == "level":
        if not rest:
            return CommandResult(
                error=True,
                message=f"Current debug level: {dm.level()}. Use /debug level 1|2|3 to change.",
            )
        try:
            n = int(rest[0])
        except ValueError:
            return CommandResult(error=True, message="Level must be 1, 2, or 3.")
        dm.set_level(n)
        return CommandResult(
            message=f"Debug level set to {dm.level()}",
            action="debug_hud_update",
        )

    if sub == "panel":
        return CommandResult(action="debug_panel_toggle")

    if sub == "api":
        new_state = dm.toggle_api_logging()
        label = "ON" if new_state else "OFF"
        return CommandResult(message=f"API logging {label}")

    # ── guard: require debug mode active for inspection commands ──────────
    _inspection_cmds = {
        "prompt",
        "timing",
        "stopreason",
        "tokens",
        "tps",
        "context",
        "diff",
        "chunks",
        "embeddings",
        "raginject",
        "tools",
        "agent",
        "tooldiff",
        "latency",
        "compare",
        "plugins",
        "replay",
        "perf",
        "export",
    }
    if sub in _inspection_cmds and not dm.is_active():
        return CommandResult(
            error=True,
            message="Debug mode is not active. Run /debug on first.",
        )

    # ── inspection commands ───────────────────────────────────────────────
    if sub == "prompt":
        return _handle_prompt(dm, rest)

    if sub == "timing":
        return _handle_timing(dm, rest)

    if sub == "stopreason":
        return _handle_stopreason(dm)

    if sub == "tokens":
        return _handle_tokens(dm)

    if sub == "tps":
        return _handle_tps(dm)

    if sub == "context":
        return _handle_context(dm, state)

    if sub == "diff":
        return _handle_diff(dm, rest)

    if sub == "chunks":
        return _handle_chunks(dm)

    if sub == "embeddings":
        return _handle_embeddings(dm)

    if sub == "raginject":
        return _handle_raginject(dm)

    if sub == "tools":
        return _handle_tools(dm)

    if sub == "agent":
        return _handle_agent(dm)

    if sub == "tooldiff":
        return _handle_tooldiff(dm, rest)

    if sub == "latency":
        return _handle_latency(dm, rest_str)

    if sub == "compare":
        return _handle_compare(ctx, state, rest)

    if sub == "plugins":
        return _handle_plugins(dm)

    if sub == "replay":
        return _handle_replay(dm, ctx, state, rest)

    if sub == "perf":
        return _handle_perf(dm)

    if sub == "export":
        return _handle_export(dm, ctx, rest_str)

    # ── V4 MMOS inspection ────────────────────────────────────────────────
    if sub == "routing":
        return _handle_routing(dm)

    if sub == "plan":
        return _handle_plan(dm)

    if sub == "ratelimit":
        return _handle_ratelimit(dm)

    # ── fallback / help ───────────────────────────────────────────────────
    if sub in ("help", ""):
        lines = [f"Debug mode: {'ON' if dm.is_active() else 'OFF'} (Level {dm.level()})\n"]
        lines.append("/debug subcommands:")
        for cmd, desc in _DEBUG_HELP_TABLE.items():
            lines.append(f"  /debug {cmd:<30} {desc}")
        return CommandResult(message="\n".join(lines))

    return CommandResult(
        error=True,
        message=f"Unknown debug subcommand '{sub}'. Try /debug help.",
    )


# ── individual subcommand handlers ────────────────────────────────────────────


def _get_record(dm: object, rest: list[str]) -> tuple[RequestDebugRecord | None, str | None]:
    """Resolve the target record: by number if given, else latest."""
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    if rest:
        try:
            n = int(rest[0])
            rec = dm.get(n)
            if rec is None:
                return None, f"No debug record #{n} found."
        except ValueError:
            rec = dm.latest()
    else:
        rec = dm.latest()
    if rec is None:
        return None, "No debug records yet. Send a message first."
    return rec, None


def _handle_prompt(dm: object, rest: list[str]) -> CommandResult:
    rec, err = _get_record(dm, rest)
    if err:
        return CommandResult(error=True, message=err)
    assert rec is not None
    from anythink.debug.formatters import format_prompt_payload

    return CommandResult(message=format_prompt_payload(rec), action="debug_display")


def _handle_timing(dm: object, rest: list[str]) -> CommandResult:
    rec, err = _get_record(dm, rest)
    if err:
        return CommandResult(error=True, message=err)
    assert rec is not None
    from anythink.debug.formatters import format_timing_breakdown

    return CommandResult(message=format_timing_breakdown(rec), action="debug_display")


def _handle_stopreason(dm: object) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")
    from anythink.debug.formatters import format_stop_reason

    return CommandResult(message=format_stop_reason(rec), action="debug_display")


def _handle_tokens(dm: object) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")
    from anythink.debug.formatters import format_token_trace

    return CommandResult(message=format_token_trace(rec), action="debug_display")


def _handle_tps(dm: object) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")
    if rec.tokens_per_second is None:
        return CommandResult(message="Tokens per second: not available (no usage data returned).")
    return CommandResult(
        message=f"Tokens per second: {rec.tokens_per_second:.1f} tok/s  "
        f"({rec.completion_tokens} tokens in {rec.stream_duration_ms():.0f}ms)"
    )


def _handle_context(dm: object, state: object) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    from anythink.debug.formatters import format_context_window

    return CommandResult(
        message=format_context_window(state, rec),
        action="debug_display",
    )


def _handle_diff(dm: object, rest: list[str]) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    records = dm.all_records()
    if len(records) < 2:
        return CommandResult(error=True, message="Need at least 2 recorded requests to diff.")
    if len(rest) >= 2:
        try:
            a = dm.get(int(rest[0]))
            b = dm.get(int(rest[1]))
        except (ValueError, TypeError):
            return CommandResult(error=True, message="Usage: /debug diff [n1] [n2]")
    else:
        b = records[-1]
        a = records[-2]
    if a is None or b is None:
        return CommandResult(error=True, message="Could not find the requested records.")
    from anythink.debug.formatters import format_prompt_diff

    return CommandResult(message=format_prompt_diff(a, b), action="debug_display")


def _handle_chunks(dm: object) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")
    from anythink.debug.formatters import format_rag_chunks

    return CommandResult(message=format_rag_chunks(rec), action="debug_display")


def _handle_embeddings(dm: object) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")
    from anythink.debug.formatters import format_embeddings

    return CommandResult(message=format_embeddings(rec), action="debug_display")


def _handle_raginject(dm: object) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")
    from anythink.debug.formatters import format_rag_inject

    return CommandResult(message=format_rag_inject(rec), action="debug_display")


def _handle_tools(dm: object) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")
    from anythink.debug.formatters import format_tool_trace

    return CommandResult(message=format_tool_trace(rec), action="debug_display")


def _handle_agent(dm: object) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")
    from anythink.debug.formatters import format_agent_log

    return CommandResult(message=format_agent_log(rec), action="debug_display")


def _handle_tooldiff(dm: object, rest: list[str]) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    records = dm.all_records()
    if len(records) < 2:
        return CommandResult(error=True, message="Need at least 2 recorded requests to diff.")
    if len(rest) >= 2:
        try:
            a = dm.get(int(rest[0]))
            b = dm.get(int(rest[1]))
        except (ValueError, TypeError):
            return CommandResult(error=True, message="Usage: /debug tooldiff [n1] [n2]")
    else:
        b = records[-1]
        a = records[-2]
    if a is None or b is None:
        return CommandResult(error=True, message="Could not find the requested records.")
    from anythink.debug.formatters import format_tool_diff

    return CommandResult(message=format_tool_diff(a, b), action="debug_display")


def _handle_latency(dm: object, rest_str: str) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    records = dm.all_records()
    if not records:
        return CommandResult(error=True, message="No debug records yet.")
    from anythink.debug.formatters import format_latency_chart

    return CommandResult(message=format_latency_chart(records), action="debug_display")


def _handle_compare(ctx: object, state: object, rest: list[str]) -> CommandResult:
    if not rest:
        return CommandResult(
            error=True,
            message="Usage: /debug compare <alias1> <alias2> [alias3...]",
        )
    return CommandResult(
        action="compare_request",
        message=f"Sending to {len(rest)} providers: {', '.join(rest)}",
        extra={"aliases": rest, "debug_compare": True},
    )


def _handle_plugins(dm: object) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")
    from anythink.debug.formatters import format_plugin_trace

    return CommandResult(message=format_plugin_trace(rec), action="debug_display")


def _handle_replay(dm: object, ctx: object, state: object, rest: list[str]) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)

    provider_override: str | None = None
    record_id: int | None = None
    i = 0
    while i < len(rest):
        if rest[i] == "--provider" and i + 1 < len(rest):
            provider_override = rest[i + 1]
            i += 2
        else:
            import contextlib

            with contextlib.suppress(ValueError):
                record_id = int(rest[i])
            i += 1

    if record_id is not None:
        rec = dm.get(record_id)
        if rec is None:
            return CommandResult(error=True, message=f"No debug record #{record_id} found.")
    else:
        rec = dm.latest()
        if rec is None:
            return CommandResult(error=True, message="No debug records yet.")

    return CommandResult(
        action="replay_stream",
        message=f"Replaying Request #{rec.request_id}"
        + (f" via {provider_override}" if provider_override else ""),
        extra={
            "record_id": rec.request_id,
            "provider_alias": provider_override,
        },
    )


def _handle_perf(dm: object) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    records = dm.all_records()
    if not records:
        return CommandResult(error=True, message="No debug records yet.")
    from anythink.debug.formatters import format_perf_summary

    return CommandResult(message=format_perf_summary(records), action="debug_display")


def _handle_export(dm: object, ctx: object, rest_str: str) -> CommandResult:
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    if not dm.all_records():
        return CommandResult(error=True, message="No debug records to export.")

    from datetime import datetime

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    export_dir = ctx.paths.debug_exports_dir
    export_dir.mkdir(parents=True, exist_ok=True)

    use_txt = "--format txt" in rest_str
    if use_txt:
        path = export_dir / f"debug_{ts}.txt"
        dm.export_txt(path)
    else:
        path = export_dir / f"debug_{ts}.json"
        dm.export_json(path)

    return CommandResult(message=f"Debug log exported to {path}")


# ── V4 MMOS debug handlers ───────────────────────────────────────────────────


def _handle_routing(dm: object) -> CommandResult:
    """Show the routing decision stored on the latest debug record."""
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")

    rd = rec.routing_decision
    if rd is None:
        return CommandResult(
            message="No MMOS routing decision found on the latest record.\n"
            "Enable MMOS (/optimize toggle) and send a query to capture routing data.",
            action="debug_display",
        )

    lines = [
        "── MMOS Routing Decision ──────────────────────────────────────",
        f"  Strategy:           {rd.strategy}",
        f"  Primary model:      {rd.primary_model}",
        f"  Plan Mode:          {'yes' if rd.plan_mode else 'no'}",
        f"  Confidence:         {rd.confidence:.2f}",
        f"  Reason:             {rd.reason}",
    ]
    if rd.phase_models:
        lines.append(f"  Phase models:       {', '.join(rd.phase_models)}")
    if rd.recombination_model:
        lines.append(f"  Recombination:      {rd.recombination_model}")
    lines.append("────────────────────────────────────────────────────────────────")
    return CommandResult(message="\n".join(lines), action="debug_display")


def _handle_plan(dm: object) -> CommandResult:
    """Show the Plan Mode execution trace stored on the latest debug record."""
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")

    plan = rec.plan_trace
    if plan is None:
        return CommandResult(
            message="No Plan Mode trace found on the latest record.\n"
            "Trigger a Plan Mode query to capture plan execution data.",
            action="debug_display",
        )

    lines = [
        "── Plan Mode Execution Trace ──────────────────────────────────",
        f"  Plan ID:    {plan.plan_id}",
        f"  Status:     {plan.status}",
        f"  Query:      {plan.original_query[:60]}{'…' if len(plan.original_query) > 60 else ''}",
        f"  Phases:     {len(plan.phases)}",
        f"  Est. tokens: {plan.total_estimated_tokens:,}",
        "",
    ]
    for phase in plan.phases:
        model = phase.actual_model or phase.model_id
        lines.append(
            f"  [{phase.status:>8}]  Phase {phase.phase_num}: {phase.title}"
            f"  ({model}, {phase.elapsed_s:.1f}s)"
        )
    lines += [
        "",
        f"  Final output: {len(plan.final_output):,} chars",
        "────────────────────────────────────────────────────────────────",
    ]
    return CommandResult(message="\n".join(lines), action="debug_display")


def _handle_ratelimit(dm: object) -> CommandResult:
    """Show the rate limit event log stored on the latest debug record."""
    from anythink.debug.manager import DebugManager

    assert isinstance(dm, DebugManager)
    rec = dm.latest()
    if rec is None:
        return CommandResult(error=True, message="No debug records yet.")

    events = rec.rate_limit_events
    if not events:
        return CommandResult(
            message="No rate limit events recorded on the latest request.\n"
            "Rate limit events are captured when a model is at its limit during an MMOS query.",
            action="debug_display",
        )

    lines = ["── Rate Limit Events ──────────────────────────────────────────"]
    for ev in events:
        lines.append(f"  {ev}")
    lines.append("────────────────────────────────────────────────────────────────")
    return CommandResult(message="\n".join(lines), action="debug_display")


# ── registration ──────────────────────────────────────────────────────────────


def register_debug_commands(registry: CommandRegistry) -> None:
    """Register the /debug command namespace."""
    registry.register(
        SlashCommand(
            "debug",
            "Debug mode and inspection tools",
            _debug_handler,
            "/debug [on|off|toggle|level 1-3|panel|prompt|timing|...]",
        )
    )
