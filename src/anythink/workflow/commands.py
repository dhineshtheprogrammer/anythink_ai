"""Slash command handlers for the /workflow namespace (MMWE)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anythink.commands.base import CommandResult, SlashCommand
from anythink.exceptions import WorkflowError

if TYPE_CHECKING:
    from anythink.app.chat import ChatState
    from anythink.app.context import AppContext
    from anythink.commands.registry import CommandRegistry
    from anythink.workflow.models import WorkflowPlan


_WORKFLOW_HELP_TABLE: dict[str, str] = {
    'run "<task>"': "Plan and execute a task as a multi-stage workflow",
    "run <name>": "Execute a saved workflow by name",
    "run ... --dry-run": "Show the workflow plan without executing",
    "new": "Start the workflow creation wizard",
    "list": "List all saved workflows",
    "show <name>": "Display a saved workflow plan",
    "edit <name>": "Open a saved workflow for editing",
    "delete <name>": "Delete a saved workflow",
    "rename <old> <new>": "Rename a saved workflow",
    "stop": "Stop the currently running workflow",
    "pause": "Pause the currently running workflow",
    "resume": "Resume a paused workflow",
    "status": "Show the status of the running workflow",
    "panel": "Toggle the live workflow progress panel",
    "logs": "List recent workflow execution logs",
    "logs last": "Open the most recent log file",
    "logs show <n>": "Open log file n (1 = most recent)",
    "manifest show": "Display the current capability manifest",
    "manifest refresh": "Rebuild and write the manifest to disk",
    "manifest path": "Show the manifest file path",
    "registry list": "List all aliases and their workflow tags",
    "registry tags <alias>": "Show tags for an alias",
    "registry add-tag <alias> <tag>": "Add a capability tag to an alias",
    "registry remove-tag <alias> <tag>": "Remove a tag from an alias",
    "registry fallback <alias> <fb>": "Set the fallback alias for an alias",
    "registry fallback-chain <alias>": "Show the full fallback chain",
}

# Maximum log entries shown by /workflow logs
_LOGS_DISPLAY_LIMIT = 20


# ---------------------------------------------------------------------------
# Top-level router
# ---------------------------------------------------------------------------


async def _workflow_handler(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Route /workflow <subcommand> to the appropriate handler."""
    args = args.strip()
    if not args or args.lower() == "help":
        return _wf_help()

    sub, _, rest = args.partition(" ")
    sub = sub.lower()
    rest = rest.strip()

    if sub == "run":
        return await _wf_run(ctx, rest)
    if sub == "new":
        return CommandResult(action="workflow_new_wizard")
    if sub == "list":
        return _wf_list(ctx)
    if sub == "show":
        return _wf_show(ctx, rest)
    if sub == "edit":
        return _wf_edit(ctx, rest)
    if sub == "delete":
        return _wf_delete(ctx, rest)
    if sub == "rename":
        return _wf_rename(ctx, rest.split())
    if sub == "stop":
        return CommandResult(action="workflow_stop")
    if sub == "pause":
        return CommandResult(action="workflow_pause")
    if sub == "resume":
        return CommandResult(action="workflow_resume")
    if sub == "status":
        return CommandResult(action="workflow_status_request")
    if sub == "panel":
        return CommandResult(action="workflow_panel_toggle")
    if sub == "logs":
        return _wf_logs(ctx, rest)
    if sub == "manifest":
        return _wf_manifest(ctx, rest)
    if sub == "registry":
        return _wf_registry(ctx, rest)

    return CommandResult(
        error=True,
        message=(
            f"Unknown /workflow subcommand '{sub}'. "
            "Use /workflow help to see available subcommands."
        ),
    )


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def _wf_help() -> CommandResult:
    lines = ["/workflow subcommands:"]
    for cmd, desc in _WORKFLOW_HELP_TABLE.items():
        lines.append(f"  /workflow {cmd:<44} {desc}")
    return CommandResult(message="\n".join(lines))


# ---------------------------------------------------------------------------
# run / dry-run
# ---------------------------------------------------------------------------


async def _wf_run(ctx: AppContext, rest: str) -> CommandResult:
    """Handle /workflow run [--dry-run] ("<task>" | <name>)."""
    dry_run = "--dry-run" in rest
    text = rest.replace("--dry-run", "").strip()

    if not text:
        return CommandResult(
            error=True,
            message=(
                'Usage: /workflow run "<task description>"  ' "or  /workflow run <saved-name>"
            ),
        )

    # Quoted text → raw task string for the planner
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        task = text[1:-1].strip()
        if not task:
            return CommandResult(error=True, message="Task description cannot be empty.")
        action = "workflow_dry_run_request" if dry_run else "workflow_run_request"
        return CommandResult(action=action, extra={"task": task, "is_named": False})

    # Unquoted → try as a saved workflow name first
    try:
        ctx.workflow_storage.load(text)
        action = "workflow_dry_run_request" if dry_run else "workflow_run_request"
        return CommandResult(action=action, extra={"name": text, "is_named": True})
    except WorkflowError:
        # Not a saved name — treat as unquoted task description
        action = "workflow_dry_run_request" if dry_run else "workflow_run_request"
        return CommandResult(action=action, extra={"task": text, "is_named": False})


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def _wf_list(ctx: AppContext) -> CommandResult:
    names = ctx.workflow_storage.list_names()
    if not names:
        return CommandResult(
            message=("No saved workflows. " 'Use /workflow run "<task>" to plan and save one.')
        )
    lines = [f"Saved workflows ({len(names)}):"]
    for name in names:
        lines.append(f"  • {name}")
    return CommandResult(message="\n".join(lines))


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def _wf_show(ctx: AppContext, name: str) -> CommandResult:
    if not name:
        return CommandResult(error=True, message="Usage: /workflow show <name>")
    try:
        plan = ctx.workflow_storage.load(name)
    except WorkflowError as exc:
        return CommandResult(error=True, message=exc.user_message)
    return CommandResult(message=_format_plan(plan))


def _format_plan(plan: WorkflowPlan) -> str:
    """Render a WorkflowPlan as a human-readable string."""
    lines = [
        f"Workflow : {plan.name}",
        f"Trigger  : {plan.trigger}",
    ]
    if plan.estimated_duration_s:
        lines.append(f"Est. time: {plan.estimated_duration_s}s")
    lines += ["", f"Stages ({len(plan.stages)}):"]
    for i, stage in enumerate(plan.stages, 1):
        tags: list[str] = []
        if stage.is_parallel:
            tags.append("parallel")
        if stage.is_destructive:
            tags.append("DESTRUCTIVE")
        tag_str = f"  [{', '.join(tags)}]" if tags else ""
        label = stage.label or stage.id
        lines.append(f"  {i}. [{stage.type.value}] {label}{tag_str}")
        if stage.model_alias:
            lines.append(f"       model: {stage.model_alias}")
        if stage.tool_name:
            lines.append(f"       tool : {stage.tool_name}")
    if plan.models_used:
        lines.append(f"\nModels     : {', '.join(plan.models_used)}")
    if plan.mcp_servers_used:
        lines.append(f"MCP servers: {', '.join(plan.mcp_servers_used)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


def _wf_edit(ctx: AppContext, name: str) -> CommandResult:
    if not name:
        return CommandResult(error=True, message="Usage: /workflow edit <name>")
    try:
        ctx.workflow_storage.load(name)  # verify the workflow exists
    except WorkflowError as exc:
        return CommandResult(error=True, message=exc.user_message)
    return CommandResult(action="workflow_edit_request", extra={"name": name})


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def _wf_delete(ctx: AppContext, name: str) -> CommandResult:
    if not name:
        return CommandResult(error=True, message="Usage: /workflow delete <name>")
    try:
        ctx.workflow_storage.delete(name)
    except WorkflowError as exc:
        return CommandResult(error=True, message=exc.user_message)
    return CommandResult(message=f"Workflow '{name}' deleted.")


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------


def _wf_rename(ctx: AppContext, parts: list[str]) -> CommandResult:
    if len(parts) < 2:
        return CommandResult(error=True, message="Usage: /workflow rename <old> <new>")
    old, new = parts[0], parts[1]
    try:
        ctx.workflow_storage.rename(old, new)
    except WorkflowError as exc:
        return CommandResult(error=True, message=exc.user_message)
    return CommandResult(message=f"Workflow '{old}' renamed to '{new}'.")


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


def _wf_logs(ctx: AppContext, rest: str) -> CommandResult:
    """Handle /workflow logs [last | show <n>]."""
    logger = ctx.workflow_engine._logger
    sub, _, rest2 = rest.partition(" ")
    sub = sub.lower()
    rest2 = rest2.strip()

    if sub == "last":
        path = logger.latest_log()
        if path is None:
            return CommandResult(message="No workflow logs found.")
        return CommandResult(action="open_file_in_editor", extra={"path": str(path)})

    if sub == "show":
        if not rest2:
            return CommandResult(error=True, message="Usage: /workflow logs show <n>")
        logs = logger.list_logs()
        if not logs:
            return CommandResult(message="No workflow logs found.")
        try:
            idx = int(rest2) - 1  # 1-based → 0-based
            if idx < 0 or idx >= len(logs):
                return CommandResult(
                    error=True,
                    message=f"Log index {rest2} out of range (1–{len(logs)}).",
                )
            path = logs[idx]
        except ValueError:
            matches = [p for p in logs if rest2 in p.name]
            if not matches:
                return CommandResult(error=True, message=f"No log matching '{rest2}'.")
            path = matches[0]
        return CommandResult(action="open_file_in_editor", extra={"path": str(path)})

    # Default: list recent logs
    logs = logger.list_logs()
    if not logs:
        return CommandResult(message="No workflow logs found.")
    lines = [f"Workflow logs ({len(logs)}):"]
    for i, p in enumerate(logs[:_LOGS_DISPLAY_LIMIT], 1):
        lines.append(f"  {i:>3}. {p.name}")
    if len(logs) > _LOGS_DISPLAY_LIMIT:
        lines.append(f"  ... and {len(logs) - _LOGS_DISPLAY_LIMIT} more")
    return CommandResult(message="\n".join(lines))


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------


def _wf_manifest(ctx: AppContext, rest: str) -> CommandResult:
    """Handle /workflow manifest [show | refresh | path]."""
    sub, _, _ = rest.partition(" ")
    sub = sub.lower()

    if sub == "show":
        text = ctx.workflow_manifest.load()
        if not text:
            return CommandResult(
                message=("Manifest is empty. " "Run /workflow manifest refresh to rebuild it.")
            )
        return CommandResult(message=text)

    if sub == "refresh":
        ctx.workflow_manifest.refresh(
            model_registry=ctx.model_registry,
            mcp_manager=ctx.mcp_manager,
            workflow_registry=ctx.workflow_registry,
            workflow_storage=ctx.workflow_storage,
        )
        return CommandResult(message=f"Manifest refreshed → {ctx.workflow_manifest.path}")

    if sub == "path":
        return CommandResult(message=str(ctx.workflow_manifest.path))

    return CommandResult(
        error=True,
        message="Usage: /workflow manifest show | refresh | path",
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


def _wf_registry(ctx: AppContext, rest: str) -> CommandResult:
    """Handle /workflow registry <subcommand> [args...]."""
    sub, _, rest2 = rest.partition(" ")
    sub = sub.lower()
    args = rest2.split()

    if not sub or sub == "list":
        aliases = ctx.workflow_registry.all_aliases()
        if not aliases:
            return CommandResult(
                message=(
                    "Workflow registry is empty. "
                    "Use /workflow registry add-tag <alias> <tag> to add entries."
                )
            )
        lines = [f"Workflow registry ({len(aliases)} entries):"]
        for entry in aliases:
            tags_str = ", ".join(entry.get("tags") or []) or "(none)"
            fb = entry.get("fallback") or ""
            fb_str = f"  → {fb}" if fb else ""
            inferred = " [inferred]" if entry.get("inferred") else ""
            lines.append(f"  {entry['alias']:<30} tags: {tags_str}{fb_str}{inferred}")
        return CommandResult(message="\n".join(lines))

    if sub == "tags":
        if not args:
            return CommandResult(error=True, message="Usage: /workflow registry tags <alias>")
        alias = args[0]
        tags = ctx.workflow_registry.get_tags(alias)
        if not tags:
            return CommandResult(message=f"'{alias}' has no explicit tags (may be inferred).")
        return CommandResult(message=f"Tags for '{alias}': {', '.join(tags)}")

    if sub == "add-tag":
        if len(args) < 2:
            return CommandResult(
                error=True, message="Usage: /workflow registry add-tag <alias> <tag>"
            )
        alias, tag = args[0], args[1]
        ctx.workflow_registry.add_tag(alias, tag)
        return CommandResult(message=f"Tag '{tag}' added to '{alias}'.")

    if sub == "remove-tag":
        if len(args) < 2:
            return CommandResult(
                error=True, message="Usage: /workflow registry remove-tag <alias> <tag>"
            )
        alias, tag = args[0], args[1]
        ctx.workflow_registry.remove_tag(alias, tag)
        return CommandResult(message=f"Tag '{tag}' removed from '{alias}'.")

    if sub == "fallback":
        if len(args) < 2:
            return CommandResult(
                error=True,
                message="Usage: /workflow registry fallback <alias> <fallback-alias>",
            )
        alias, fb = args[0], args[1]
        ctx.workflow_registry.set_fallback(alias, fb)
        return CommandResult(message=f"Fallback for '{alias}' set to '{fb}'.")

    if sub in ("fallback-chain", "chain"):
        if not args:
            return CommandResult(
                error=True, message="Usage: /workflow registry fallback-chain <alias>"
            )
        alias = args[0]
        chain = ctx.workflow_registry.get_fallback_chain(alias)
        if len(chain) <= 1:
            return CommandResult(message=f"'{alias}' has no fallback chain.")
        return CommandResult(message=f"Fallback chain for '{alias}': {' → '.join(chain)}")

    return CommandResult(
        error=True,
        message=(
            f"Unknown /workflow registry subcommand '{sub}'. "
            "Use: list | tags | add-tag | remove-tag | fallback | fallback-chain"
        ),
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_workflow_commands(registry: CommandRegistry) -> None:
    """Register the /workflow command namespace."""
    registry.register(
        SlashCommand(
            "workflow",
            "Multi-model workflow engine — plan, run, and manage multi-stage AI pipelines",
            _workflow_handler,
            "/workflow run|list|show|delete|rename|stop|pause|resume|status|logs|manifest|registry",
        )
    )
