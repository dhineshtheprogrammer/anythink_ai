"""Slash command handlers for the /optimize and /mode namespaces (V4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anythink.commands.base import CommandResult, SlashCommand

if TYPE_CHECKING:
    from anythink.app.chat import ChatState
    from anythink.app.context import AppContext
    from anythink.commands.registry import CommandRegistry


# ── Help tables ───────────────────────────────────────────────────────────────

_OPTIMIZE_HELP_TABLE: dict[str, str] = {
    "": "Open the full optimization settings panel",
    "status": "Show current optimization configuration at a glance",
    "toggle": "Enable or disable the optimization engine",
    "mode online|offline|auto": "Switch between online/offline/auto model mode",
    "routing category|token_length|combined": "Configure routing strategy",
    "history semantic|recency|model_decides": "Set context history selection mode",
    "history max <tokens>": "Set maximum history token budget",
    "priority quality|reliability|hybrid": "Set quality vs reliability priority",
    "plan on|off": "Enable or disable Plan Mode",
    "plan approval on|off": "Require approval before plan execution",
    "ensemble routing|ensemble|chaining|decompose": "Set default mixing strategy",
    "ensemble count <n>": "Set number of models for ensemble mode (2-5)",
    "ratelimit": "View live rate limit status for all models",
    "registry": "Open the model capability registry viewer",
    "registry add": "Add a new model entry",
    "registry edit <id>": "Edit an existing model entry",
    "registry delete <id>": "Remove a user-added model entry",
    "registry reset <id>": "Reset a model entry to its bundled value",
    "registry export": "Export the full registry to a JSON file",
    "registry import <file>": "Import model entries from a JSON file",
    "microprompt": "Toggle the pre-query intent micro-prompt on/off",
    "reset": "Reset all optimization settings to defaults",
}

_MODE_VALID = frozenset({"online", "offline", "auto"})
_PRIORITY_VALID = frozenset({"quality", "reliability", "hybrid"})
_HISTORY_MODES = frozenset({"semantic", "recency", "model_decides"})
_ROUTING_STRATEGIES = frozenset({"category", "token_length", "combined"})
_MIXING_MODES = frozenset({"routing", "ensemble", "chaining", "decompose"})


# ── /mode handler ─────────────────────────────────────────────────────────────


async def _mode_handler(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Handle /mode online | offline | auto."""
    mode = args.strip().lower()
    if mode not in _MODE_VALID:
        valid = " | ".join(sorted(_MODE_VALID))
        return CommandResult(
            error=True,
            message=f"Unknown mode '{mode}'. Valid options: {valid}",
        )
    ctx.mmos_settings.update(mode=mode)
    return CommandResult(
        message=f"Mode set to: {mode.upper()}",
        action="mmos_hud_update",
    )


# ── /optimize dispatcher ──────────────────────────────────────────────────────


async def _optimize_handler(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Route /optimize subcommands."""
    parts = args.strip().split()
    sub = parts[0].lower() if parts else ""
    rest = parts[1:] if len(parts) > 1 else []

    if sub == "" or sub == "panel":
        return CommandResult(action="open_optimize_panel")

    if sub == "status":
        return _opt_status(ctx)

    if sub == "toggle":
        return _opt_toggle(ctx)

    if sub == "mode":
        mode_arg = rest[0].lower() if rest else ""
        return await _mode_handler(ctx, mode_arg, state, registry)

    if sub == "routing":
        return _opt_routing(ctx, rest)

    if sub == "history":
        return _opt_history(ctx, rest)

    if sub == "priority":
        return _opt_priority(ctx, rest)

    if sub == "plan":
        return _opt_plan(ctx, rest)

    if sub == "ensemble":
        return _opt_ensemble(ctx, rest)

    if sub == "ratelimit":
        return CommandResult(action="open_ratelimit_panel")

    if sub == "registry":
        return _opt_registry(ctx, rest)

    if sub == "microprompt":
        return _opt_microprompt(ctx)

    if sub == "reset":
        return CommandResult(
            message="This will reset ALL optimization settings to defaults.",
            action="optimize_reset_confirm",
        )

    if sub in ("help", "?"):
        return _opt_help()

    return CommandResult(
        error=True,
        message=f"Unknown subcommand '/optimize {sub}'. Try /optimize help.",
    )


# ── Subcommand handlers ───────────────────────────────────────────────────────


def _opt_status(ctx: AppContext) -> CommandResult:
    """Return a compact status snapshot."""
    s = ctx.mmos_settings.get()
    rl_status = ctx.rate_limit_manager.get_status()
    at_limit = [w.model_id for w in rl_status if ctx.rate_limit_manager.is_at_rpm_limit(w.model_id)]

    lines = [
        "── Optimization Status ────────────────────────────────────",
        f"  Engine:        {'ENABLED' if s.enabled else 'DISABLED'}",
        f"  Mode:          {s.mode.upper()}",
        f"  Priority:      {s.priority}",
        f"  Routing:       {s.routing_strategy}",
        f"  Mixing:        {s.mixing_mode}",
        f"  History mode:  {s.history_mode}  (max {s.history_max_tokens} tokens)",
        f"  Plan Mode:     {'on' if s.plan_mode_enabled else 'off'}"
        + ("  [approval required]" if s.plan_approval_required else ""),
        f"  Micro-prompt:  {'on' if s.microprompt_enabled else 'off'}",
        f"  Orchestration: {s.orchestration_mode}",
    ]

    if s.fallback_order:
        lines.append(f"  Fallback:      {' → '.join(s.fallback_order)}")

    total_models = len(ctx.mmos_registry.all())
    online = len(ctx.mmos_registry.available_online())
    offline = len(ctx.mmos_registry.available_offline())
    lines += [
        f"  Registry:      {total_models} models ({online} online, {offline} local)",
    ]

    if at_limit:
        lines.append(f"  Rate limited:  {', '.join(at_limit)}")

    lines.append("────────────────────────────────────────────────────────────")
    return CommandResult(message="\n".join(lines))


def _opt_toggle(ctx: AppContext) -> CommandResult:
    s = ctx.mmos_settings.get()
    new_enabled = not s.enabled
    ctx.mmos_settings.update(enabled=new_enabled)
    label = "ENABLED" if new_enabled else "DISABLED"
    return CommandResult(
        message=f"Optimization engine {label}.",
        action="mmos_hud_update",
    )


def _opt_routing(ctx: AppContext, rest: list[str]) -> CommandResult:
    if not rest:
        s = ctx.mmos_settings.get()
        return CommandResult(
            message=f"Current routing strategy: {s.routing_strategy}\n"
            f"Options: {' | '.join(sorted(_ROUTING_STRATEGIES))}"
        )
    strategy = rest[0].lower()
    if strategy not in _ROUTING_STRATEGIES:
        return CommandResult(
            error=True,
            message=f"Invalid routing strategy '{strategy}'. Options: "
            + " | ".join(sorted(_ROUTING_STRATEGIES)),
        )
    ctx.mmos_settings.update(routing_strategy=strategy)
    return CommandResult(
        message=f"Routing strategy set to: {strategy}",
        action="mmos_hud_update",
    )


def _opt_history(ctx: AppContext, rest: list[str]) -> CommandResult:
    if not rest:
        s = ctx.mmos_settings.get()
        return CommandResult(
            message=f"History mode: {s.history_mode}  |  Max tokens: {s.history_max_tokens}\n"
            f"Usage: /optimize history [mode]  or  /optimize history max <tokens>"
        )

    sub = rest[0].lower()

    if sub == "max":
        if len(rest) < 2:
            return CommandResult(error=True, message="Usage: /optimize history max <tokens>")
        try:
            n = int(rest[1])
        except ValueError:
            return CommandResult(error=True, message="Token count must be an integer.")
        if n < 128:
            return CommandResult(error=True, message="Minimum history budget is 128 tokens.")
        ctx.mmos_settings.update(history_max_tokens=n)
        return CommandResult(message=f"History token budget set to {n}.")

    if sub not in _HISTORY_MODES:
        return CommandResult(
            error=True,
            message=f"Unknown history mode '{sub}'. Options: "
            + " | ".join(sorted(_HISTORY_MODES)),
        )
    ctx.mmos_settings.update(history_mode=sub)
    return CommandResult(
        message=f"History selection mode set to: {sub}",
        action="mmos_hud_update",
    )


def _opt_priority(ctx: AppContext, rest: list[str]) -> CommandResult:
    if not rest:
        s = ctx.mmos_settings.get()
        return CommandResult(
            message=f"Current priority: {s.priority}\n"
            f"Options: {' | '.join(sorted(_PRIORITY_VALID))}"
        )
    priority = rest[0].lower()
    if priority not in _PRIORITY_VALID:
        return CommandResult(
            error=True,
            message=f"Invalid priority '{priority}'. Options: "
            + " | ".join(sorted(_PRIORITY_VALID)),
        )
    ctx.mmos_settings.update(priority=priority)
    return CommandResult(
        message=f"Priority set to: {priority}",
        action="mmos_hud_update",
    )


def _opt_plan(ctx: AppContext, rest: list[str]) -> CommandResult:
    if not rest:
        s = ctx.mmos_settings.get()
        state_label = "on" if s.plan_mode_enabled else "off"
        approval_label = "on" if s.plan_approval_required else "off"
        return CommandResult(
            message=f"Plan Mode: {state_label}  |  Approval required: {approval_label}\n"
            "Usage: /optimize plan on|off  or  /optimize plan approval on|off"
        )

    sub = rest[0].lower()

    if sub == "approval":
        if len(rest) < 2:
            return CommandResult(error=True, message="Usage: /optimize plan approval on|off")
        val = rest[1].lower()
        if val not in ("on", "off"):
            return CommandResult(error=True, message="Value must be 'on' or 'off'.")
        ctx.mmos_settings.update(plan_approval_required=(val == "on"))
        return CommandResult(message=f"Plan approval requirement: {val}")

    if sub in ("on", "off"):
        ctx.mmos_settings.update(plan_mode_enabled=(sub == "on"))
        return CommandResult(
            message=f"Plan Mode: {sub}",
            action="mmos_hud_update",
        )

    return CommandResult(
        error=True,
        message="Usage: /optimize plan on|off  or  /optimize plan approval on|off",
    )


def _opt_ensemble(ctx: AppContext, rest: list[str]) -> CommandResult:
    if not rest:
        s = ctx.mmos_settings.get()
        return CommandResult(
            message=f"Mixing mode: {s.mixing_mode}  |  Ensemble count: {s.ensemble_count}\n"
            "Usage: /optimize ensemble [mode]  or  /optimize ensemble count <n>"
        )

    sub = rest[0].lower()

    if sub == "count":
        if len(rest) < 2:
            return CommandResult(error=True, message="Usage: /optimize ensemble count <2-5>")
        try:
            n = int(rest[1])
        except ValueError:
            return CommandResult(error=True, message="Count must be an integer.")
        if not (2 <= n <= 5):
            return CommandResult(error=True, message="Ensemble count must be between 2 and 5.")
        ctx.mmos_settings.update(ensemble_count=n)
        return CommandResult(message=f"Ensemble count set to {n}.")

    if sub not in _MIXING_MODES:
        return CommandResult(
            error=True,
            message=f"Invalid mixing mode '{sub}'. Options: "
            + " | ".join(sorted(_MIXING_MODES)),
        )
    ctx.mmos_settings.update(mixing_mode=sub)
    return CommandResult(
        message=f"Mixing mode set to: {sub}",
        action="mmos_hud_update",
    )


def _opt_registry(ctx: AppContext, rest: list[str]) -> CommandResult:
    sub = rest[0].lower() if rest else ""
    rest2 = rest[1:] if len(rest) > 1 else []

    if sub == "":
        return CommandResult(action="open_optimize_registry")

    if sub == "add":
        return CommandResult(action="open_optimize_registry_add")

    if sub == "edit":
        if not rest2:
            return CommandResult(error=True, message="Usage: /optimize registry edit <model-id>")
        return CommandResult(
            action="open_optimize_registry_edit",
            extra={"model_id": rest2[0]},
        )

    if sub == "delete":
        if not rest2:
            return CommandResult(error=True, message="Usage: /optimize registry delete <model-id>")
        model_id = rest2[0]
        existing = ctx.mmos_registry.get(model_id)
        if existing is None:
            return CommandResult(
                error=True,
                message=f"Model '{model_id}' not found in registry.",
            )
        ctx.mmos_registry.remove_user_entry(model_id)
        return CommandResult(message=f"Removed user entry for '{model_id}'.")

    if sub == "reset":
        if not rest2:
            return CommandResult(error=True, message="Usage: /optimize registry reset <model-id>")
        model_id = rest2[0]
        ctx.mmos_registry.reset_to_bundled(model_id)
        return CommandResult(message=f"Reset '{model_id}' to bundled defaults.")

    if sub == "export":
        from datetime import datetime
        from pathlib import Path

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        export_path = ctx.paths.exports_dir / f"model_registry_{ts}.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        ctx.mmos_registry.export_json(export_path)
        return CommandResult(message=f"Registry exported to {export_path}")

    if sub == "import":
        if not rest2:
            return CommandResult(error=True, message="Usage: /optimize registry import <file>")
        from pathlib import Path

        import_path = Path(rest2[0])
        if not import_path.exists():
            return CommandResult(error=True, message=f"File not found: {import_path}")
        try:
            count = ctx.mmos_registry.import_json(import_path)
        except Exception as exc:
            return CommandResult(error=True, message=f"Import failed: {exc}")
        return CommandResult(message=f"Imported {count} model entries from {import_path}")

    return CommandResult(
        error=True,
        message=f"Unknown registry subcommand '{sub}'. "
        "Try: add | edit | delete | reset | export | import",
    )


def _opt_microprompt(ctx: AppContext) -> CommandResult:
    s = ctx.mmos_settings.get()
    new_val = not s.microprompt_enabled
    ctx.mmos_settings.update(microprompt_enabled=new_val)
    label = "ON" if new_val else "OFF"
    return CommandResult(
        message=f"Pre-query intent micro-prompt: {label}",
        action="mmos_hud_update",
    )


def _opt_help() -> CommandResult:
    lines = ["/optimize subcommands:"]
    for cmd, desc in _OPTIMIZE_HELP_TABLE.items():
        key = f"/optimize {cmd}" if cmd else "/optimize"
        lines.append(f"  {key:<45}  {desc}")
    return CommandResult(message="\n".join(lines))


# ── Registration ──────────────────────────────────────────────────────────────


def register_optimize_commands(registry: CommandRegistry) -> None:
    """Register the /optimize and /mode command namespaces."""
    registry.register(
        SlashCommand(
            "optimize",
            "Multi-model optimization settings and controls (V4)",
            _optimize_handler,
            "/optimize [status|toggle|mode|routing|history|priority|plan|ensemble|"
            "ratelimit|registry|microprompt|reset]",
        )
    )
    registry.register(
        SlashCommand(
            "mode",
            "Switch online/offline/auto model mode (V4)",
            _mode_handler,
            "/mode online|offline|auto",
        )
    )
