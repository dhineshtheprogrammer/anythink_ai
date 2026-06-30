"""MMAE /smart command namespace."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anythink.commands.base import CommandResult, SlashCommand

if TYPE_CHECKING:
    from anythink.app.chat import ChatState
    from anythink.app.context import AppContext
    from anythink.commands.registry import CommandRegistry
    from anythink.smart.registry import SmartRegistry

_SMART_HELP = """\
/smart on|off|toggle        Enable / disable MMAE for this session
/smart status               Show current MMAE configuration
/smart registry             Manage category-to-model assignments
/smart combiner stitch|merge  Set combiner mode
/smart format <fmt>|off     Set session output format default
/smart quality <0-100>      Set quality gate threshold
"""

_VALID_FORMATS = {"markdown", "list", "table", "code_only", "json", "summary", "detailed"}


# ──────────────────────────────────────────────────────────────────────────────
# Main handler
# ──────────────────────────────────────────────────────────────────────────────


async def _smart_handler(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("", "status"):
        return _handle_status(ctx)

    if sub == "on":
        ctx.smart_enabled = True
        return CommandResult(message="✦ Smart mode ON.", action="smart_hud_update")

    if sub == "off":
        ctx.smart_enabled = False
        return CommandResult(message="✦ Smart mode OFF.", action="smart_hud_update")

    if sub == "toggle":
        ctx.smart_enabled = not ctx.smart_enabled
        state_label = "ON" if ctx.smart_enabled else "OFF"
        return CommandResult(message=f"✦ Smart mode {state_label}.", action="smart_hud_update")

    if sub == "registry":
        return _handle_registry(ctx, rest)

    if sub == "combiner":
        return _handle_combiner(ctx, rest)

    if sub == "format":
        return _handle_format(ctx, rest)

    if sub == "quality":
        return _handle_quality(ctx, rest)

    if sub in ("help", "?"):
        return CommandResult(message=_SMART_HELP)

    return CommandResult(
        error=True,
        message=(f"Unknown /smart subcommand: {sub!r}\n" "Run /smart help for usage."),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Subcommand handlers
# ──────────────────────────────────────────────────────────────────────────────


def _handle_status(ctx: AppContext) -> CommandResult:
    from anythink.smart.categories import CATEGORIES

    sr: SmartRegistry = ctx.smart_registry
    enabled = getattr(ctx, "smart_enabled", False)
    threshold = ctx.config.smart_quality_threshold
    combiner_mode = ctx.config.smart_combiner_mode
    session_format = ctx.config.smart_session_format or "(none)"

    lines = [
        f"✦ Smart mode: {'ON' if enabled else 'OFF'}",
        f"  Quality threshold : {threshold}%",
        f"  Combiner mode     : {combiner_mode}",
        f"  Session format    : {session_format}",
        f"  Show detail       : {'yes' if ctx.config.smart_show_detail else 'no'}",
        "",
        "Category → Model assignments:",
    ]
    for cat_key in CATEGORIES:
        alias = sr.get(cat_key) or "(unset)"
        lines.append(f"  {cat_key:<16} {alias}")
    lines += [
        "",
        f"  router   : {sr.get_router() or '(unset)'}",
        f"  combiner : {sr.get_combiner() or '(unset)'}",
        f"  formatter: {sr.get_formatter() or '(unset)'}",
    ]
    return CommandResult(message="\n".join(lines))


def _handle_registry(ctx: AppContext, rest: str) -> CommandResult:
    sr: SmartRegistry = ctx.smart_registry
    parts = rest.split(None, 2)
    sub = parts[0].lower() if parts else ""
    arg1 = parts[1] if len(parts) > 1 else ""
    arg2 = parts[2] if len(parts) > 2 else ""

    from anythink.smart.categories import CATEGORIES

    if sub in ("", "show") and not arg1:
        lines = ["Category → Model:"]
        for k in CATEGORIES:
            alias = sr.get(k) or "(unset)"
            lines.append(f"  {k:<16} {alias}")
        lines += [
            f"\n  router   : {sr.get_router() or '(unset)'}",
            f"  combiner : {sr.get_combiner() or '(unset)'}",
            f"  formatter: {sr.get_formatter() or '(unset)'}",
        ]
        return CommandResult(message="\n".join(lines))

    if sub == "show" and arg1:
        cat = arg1.lower()
        if cat in CATEGORIES:
            return CommandResult(message=f"{cat}: {sr.get(cat) or '(unset)'}")
        return CommandResult(error=True, message=f"Unknown category: {cat!r}")

    if sub == "set" and arg1 and arg2:
        cat = arg1.lower()
        if cat not in CATEGORIES:
            return CommandResult(error=True, message=f"Unknown category: {cat!r}")
        sr.set(cat, arg2)
        return CommandResult(message=f"Set {cat} → {arg2}")

    if sub == "reset":
        if arg1.lower() == "all":
            sr.reset_all()
            return CommandResult(message="Reset all category assignments to defaults.")
        if arg1.lower() in CATEGORIES:
            sr.reset(arg1.lower())
            return CommandResult(message=f"Reset {arg1.lower()} to default.")
        return CommandResult(error=True, message=f"Unknown category: {arg1!r}")

    if sub == "router" and arg1:
        sr.set_router(arg1)
        return CommandResult(message=f"Router model → {arg1}")

    if sub == "combiner" and arg1:
        sr.set_combiner(arg1)
        return CommandResult(message=f"Combiner model → {arg1}")

    if sub == "formatter" and arg1:
        sr.set_formatter(arg1)
        return CommandResult(message=f"Formatter model → {arg1}")

    if sub == "fallback" and arg1:
        sr.set("general", arg1)
        return CommandResult(message=f"General fallback model → {arg1}")

    return CommandResult(
        error=True,
        message=(
            "Usage: /smart registry [show [<cat>] | set <cat> <alias> | reset <cat>|all\n"
            "       /smart registry router|combiner|formatter|fallback <alias>"
        ),
    )


def _handle_combiner(ctx: AppContext, rest: str) -> CommandResult:
    sub = rest.strip().lower()

    if sub == "stitch":
        _update_config(ctx, smart_combiner_mode="stitch")
        return CommandResult(message="Combiner mode → Stitch")

    if sub == "merge":
        _update_config(ctx, smart_combiner_mode="merge")
        return CommandResult(message="Combiner mode → Intelligent Merge")

    if sub == "show":
        return CommandResult(message=f"Combiner mode: {ctx.config.smart_combiner_mode}")

    return CommandResult(
        error=True,
        message="Usage: /smart combiner stitch|merge|show",
    )


def _handle_format(ctx: AppContext, rest: str) -> CommandResult:
    fmt = rest.strip().lower()

    if fmt == "off":
        _update_config(ctx, smart_session_format="")
        return CommandResult(message="Session format default cleared.")

    if fmt == "show":
        current = ctx.config.smart_session_format or "(none)"
        return CommandResult(message=f"Session format: {current}")

    if fmt in _VALID_FORMATS:
        _update_config(ctx, smart_session_format=fmt)
        return CommandResult(message=f"Session format → {fmt}")

    return CommandResult(
        error=True,
        message=(
            f"Unknown format: {fmt!r}\n" f"Valid formats: {', '.join(sorted(_VALID_FORMATS))}"
        ),
    )


def _handle_quality(ctx: AppContext, rest: str) -> CommandResult:
    sub = rest.strip().lower()

    if sub == "show":
        return CommandResult(message=f"Quality threshold: {ctx.config.smart_quality_threshold}%")

    try:
        val = int(sub)
    except ValueError:
        return CommandResult(error=True, message="Usage: /smart quality <0-100>|show")

    val = max(0, min(100, val))
    _update_config(ctx, smart_quality_threshold=val)
    return CommandResult(message=f"Quality threshold → {val}%")


def _update_config(ctx: AppContext, **kwargs: object) -> None:
    """Mutate ctx.config in-place (frozen → replace pattern)."""
    import dataclasses

    new_config = dataclasses.replace(ctx.config, **kwargs)  # type: ignore[arg-type]
    ctx.config_manager.save(new_config)
    ctx.config = new_config


# ──────────────────────────────────────────────────────────────────────────────
# Registration
# ──────────────────────────────────────────────────────────────────────────────


def register_smart_commands(registry: CommandRegistry) -> None:
    registry.register(
        SlashCommand(
            "smart",
            "Multi-Model Answering Engine — route questions to specialist models",
            _smart_handler,
            "/smart [on|off|toggle|status|registry|combiner|format|quality]",
        )
    )
