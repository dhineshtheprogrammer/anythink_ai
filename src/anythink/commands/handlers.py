"""Built-in slash command handlers."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from anythink.bookmarks.manager import BookmarkManager
from anythink.branch.manager import BranchManager
from anythink.commands.base import CommandResult, SlashCommand
from anythink.exceptions import FileError, MCPError, SearchError
from anythink.files.reader import ImageAttachment, TextAttachment, read_image_file, read_text_file
from anythink.mcp.models import MCPConnectConfig
from anythink.notify.notifier import NOTIFICATION_DEFAULTS, SLOW_EXEC_S, SLOW_RESPONSE_S
from anythink.providers.base import ChatMessage
from anythink.session.models import Session
from anythink.tools.exec import RUNTIMES
from anythink.voice.transcriber import VALID_MODELS

if TYPE_CHECKING:
    from anythink.app.chat import ChatState
    from anythink.app.context import AppContext
    from anythink.commands.registry import CommandRegistry


def register_commands(registry: CommandRegistry) -> None:
    """Register all built-in Anythink slash commands."""
    registry.register(SlashCommand("help", "Show available commands", _help, "/help"))
    registry.register(SlashCommand("clear", "Clear conversation history", _clear, "/clear"))
    registry.register(
        SlashCommand("history", "Show recent conversation turns", _history, "/history")
    )
    registry.register(SlashCommand("tokens", "Show context-window token usage", _tokens, "/tokens"))
    registry.register(SlashCommand("model", "Show the active provider and model", _model, "/model"))
    registry.register(
        SlashCommand(
            "persona", "Set or clear the active persona", _persona, "/persona <name> | clear"
        )
    )
    registry.register(
        SlashCommand(
            "session", "Manage saved sessions", _session, "/session <save|load|list|delete|rename>"
        )
    )
    registry.register(
        SlashCommand("file", "Attach a text file to the next message", _file, "/file <path>")
    )
    registry.register(
        SlashCommand("image", "Attach an image to the next message", _image, "/image <path>")
    )
    registry.register(SlashCommand("files", "List pending file attachments", _files, "/files"))
    registry.register(
        SlashCommand(
            "search",
            "Enable/disable web search or run a one-off search",
            _search,
            "/search on|off|<query>",
        )
    )
    registry.register(
        SlashCommand(
            "plugins",
            "List or manage installed plugins",
            _plugins,
            "/plugins [list|info|install|remove] [name]",
        )
    )
    registry.register(SlashCommand("exit", "Exit Anythink", _exit_cmd, "/exit"))
    registry.register(SlashCommand("quit", "Exit Anythink", _exit_cmd, "/quit"))
    registry.register(
        SlashCommand("rename", "Rename the current session", _rename, "/rename <new name>")
    )
    registry.register(SlashCommand("undo", "Undo the last message exchange", _undo, "/undo"))
    registry.register(
        SlashCommand(
            "bookmark",
            "Bookmark an AI response",
            _bookmark,
            "/bookmark [turn] | label <n> <text> | export [path] | search <query>",
        )
    )
    registry.register(
        SlashCommand("bookmarks", "List all bookmarks in this session", _bookmarks, "/bookmarks")
    )
    registry.register(
        SlashCommand(
            "branch",
            "Create or manage conversation branches",
            _branch,
            "/branch  |  /branch list  |  /branch switch <name>",
        )
    )
    registry.register(
        SlashCommand(
            "rag",
            "Manage RAG indexes and retrieval",
            _rag,
            "/rag list|new|use|off|rebuild|info|delete|status",
        )
    )
    registry.register(
        SlashCommand(
            "exec",
            "Run code in your local environment via PATH runtimes",
            _exec,
            "/exec <language> <code>  |  /exec mode ask|auto",
        )
    )
    registry.register(
        SlashCommand(
            "browse",
            "Fetch a web page or search the web",
            _browse,
            "/browse <url|query>  |  /browse mode ask|auto|http|headless",
        )
    )
    registry.register(
        SlashCommand(
            "mcp",
            "Manage MCP servers and call tools",
            _mcp,
            "/mcp list|tools|connect|disconnect|status|call|server",
        )
    )
    registry.register(
        SlashCommand(
            "voice",
            "Record voice and transcribe to text",
            _voice,
            "/voice  |  /voice model tiny|base|small|medium|large|turbo",
        )
    )
    registry.register(
        SlashCommand(
            "notify",
            "Manage desktop notification settings",
            _notify,
            "/notify on|off|status  |  /notify type <name> on|off",
        )
    )
    registry.register(
        SlashCommand(
            "settings",
            "Open the interactive settings menu",
            _settings_cmd,
            "/settings",
        )
    )

    # ── V3 commands ────────────────────────────────────────────────────────────
    registry.register(
        SlashCommand(
            "params",
            "View or set generation parameters for the active model alias",
            _params,
            "/params  |  /params temperature=0.8 max_tokens=2048 top_p=0.9",
        )
    )
    registry.register(
        SlashCommand(
            "cost",
            "Show estimated API spend for the current session or all time",
            _cost,
            "/cost  |  /cost today  |  /cost month  |  /cost by-model  |  /cost by-provider",
        )
    )
    registry.register(
        SlashCommand(
            "template",
            "Manage prompt templates",
            _template,
            "/template list  |  save <name> <body>  |  show <name>  |  delete <name>",
        )
    )
    registry.register(
        SlashCommand(
            "use",
            "Instantiate a prompt template and send it as a message",
            _use,
            "/use <name>  |  /use <name> key=value ...",
        )
    )
    registry.register(
        SlashCommand(
            "doctor",
            "Run diagnostics and check the health of your Anythink installation",
            _doctor,
            "/doctor",
        )
    )
    registry.register(
        SlashCommand(
            "update",
            "Check for or install Anythink updates",
            _update,
            "/update  |  /update check",
        )
    )
    registry.register(
        SlashCommand(
            "config",
            "Export or import Anythink configuration as a portable bundle",
            _config_cmd,
            "/config export [path]  |  /config import <path>",
        )
    )
    registry.register(
        SlashCommand(
            "export",
            "Export the current session to Markdown, JSON, or PDF",
            _export,
            "/export [markdown|json|pdf] [path]  |  /export --range 1-10",
        )
    )
    registry.register(
        SlashCommand(
            "compare",
            "Compare responses from multiple model aliases side-by-side",
            _compare,
            "/compare <alias1> <alias2> [alias3 ...]",
        )
    )
    registry.register(
        SlashCommand(
            "schedule",
            "Manage scheduled prompt automation",
            _schedule,
            "/schedule list  |  add <name> <cron> <prompt>  |  remove|run|enable|disable <name>",
        )
    )

    # ── V3.2 debug commands ────────────────────────────────────────────────
    from anythink.debug.commands import register_debug_commands

    register_debug_commands(registry)

    registry.register(
        SlashCommand(
            "preview",
            "Preview the fully assembled prompt before sending",
            _preview,
            "/preview",
        )
    )
    registry.register(
        SlashCommand(
            "perf",
            "Show session performance summary (alias for /debug perf)",
            _perf_alias,
            "/perf",
        )
    )


async def _help(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    if args.strip().lower() == "debug":
        from anythink.debug.commands import _DEBUG_HELP_TABLE

        dm = ctx.debug_manager
        lines = [
            f"Debug mode: {'ON' if dm.is_active() else 'OFF'} (Level {dm.level()})\n",
            "/debug subcommands:",
        ]
        for cmd, desc in _DEBUG_HELP_TABLE.items():
            lines.append(f"  /debug {cmd:<38} {desc}")
        return CommandResult(message="\n".join(lines))

    lines = ["Available commands:"]
    for name in registry.names():
        entry = registry.get(name)
        if entry is not None:
            lines.append(f"  /{name:<12} {entry.description}")
    if ctx.debug_manager.is_active():
        lines.append("\nDebug mode is ON — run /help debug for debug command reference.")
    return CommandResult(message="\n".join(lines))


async def _clear(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    return CommandResult(
        action="clear_confirm",
        message="Clear conversation? This will reset the visible chat to empty.\n"
        "Your messages are saved and reachable via /history.\n"
        "[Y] Clear  [N] Cancel",
    )


async def _history(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    if not state.history:
        return CommandResult(message="No messages yet.")

    limit = 10
    shown = state.history[-limit:]
    lines: list[str] = []
    if len(state.history) > limit:
        lines.append(f"(showing last {limit} of {len(state.history)} messages)")
    for msg in shown:
        if isinstance(msg.content, str):
            snippet = msg.content[:80] + ("…" if len(msg.content) > 80 else "")
        else:
            snippet = "[multimodal content]"
        lines.append(f"[{msg.role}] {snippet}")
    return CommandResult(message="\n".join(lines))


async def _tokens(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    used = state.total_tokens_used
    total = state.context_window
    pct = used / total * 100 if total else 0.0
    return CommandResult(message=f"Tokens: {used:,} / {total:,} ({pct:.1f}%)")


async def _model(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    return CommandResult(message=f"Provider: {state.provider.name}  Model: {state.model_id}")


async def _persona(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    if not args:
        return CommandResult(
            error=True,
            message="Usage: /persona <name>  or  /persona clear",
        )

    if args.lower() == "clear":
        state.history = [m for m in state.history if m.role != "system"]
        return CommandResult(message="Persona cleared.")

    persona = ctx.persona_manager.get(args)
    if persona is None:
        return CommandResult(error=True, message=f"Persona '{args}' not found.")

    state.history = [m for m in state.history if m.role != "system"]
    state.history.insert(0, ChatMessage(role="system", content=persona.system_prompt))
    return CommandResult(message=f"Persona '{persona.name}' activated.")


async def _session(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    parts = args.split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    if not sub:
        return CommandResult(
            error=True,
            message="Usage: /session <save|load|list|delete|rename> [args]",
        )

    if sub == "list":
        sessions = ctx.session_manager.list_sessions()
        if not sessions:
            return CommandResult(message="No saved sessions.")
        lines = ["Saved sessions:"]
        for s in sessions:
            name_part = f"  {s.name}" if s.name else ""
            ts = s.updated_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"  {s.id[:8]}…{name_part}  [{ts}]  {len(s.messages)} msg(s)")
        return CommandResult(message="\n".join(lines))

    if sub == "save":
        if rest:
            state.session_name = rest
        session = Session(
            id=state.session_id,
            provider=state.provider.name,
            model_id=state.model_id,
            messages=list(state.history),
            name=state.session_name,
        )
        ctx.session_manager.save(session)
        label = f"'{state.session_name}'" if state.session_name else state.session_id[:8] + "…"
        return CommandResult(message=f"Session {label} saved.")

    if sub == "load":
        if not rest:
            return CommandResult(error=True, message="Usage: /session load <id_or_name>")
        found = ctx.session_manager.find_by_name_or_id(rest)
        if found is None:
            return CommandResult(
                error=True, message=f"Session '{rest}' not found. Use /session list."
            )
        # Restore main branch
        state.history = list(found.messages)
        state.bookmarks = list(found.bookmarks)
        state.session_id = found.id
        state.session_name = found.name
        state.total_tokens_used = 0
        state.active_branch = "main"
        state.branches = {"main": state.history}
        state.branch_bookmarks = {"main": state.bookmarks}
        state.branch_diverges = {"main": 0}
        # Restore non-main branches
        for bname, bi in found.branches.items():
            state.branches[bname] = list(bi.messages)
            state.branch_bookmarks[bname] = list(bi.bookmarks)
            state.branch_diverges[bname] = bi.diverge_turn
        label = found.name or found.id[:8] + "…"
        return CommandResult(
            message=f"Loaded session '{label}' ({len(found.messages)} messages).",
            action="branch_hud_update",
        )

    if sub == "delete":
        if not rest:
            return CommandResult(error=True, message="Usage: /session delete <id_or_name>")
        found = ctx.session_manager.find_by_name_or_id(rest)
        if found is None:
            return CommandResult(error=True, message=f"Session '{rest}' not found.")
        ctx.session_manager.delete(found.id)
        label = found.name or found.id[:8] + "…"
        return CommandResult(message=f"Session '{label}' deleted.")

    if sub == "rename":
        rename_parts = rest.split(None, 1)
        if len(rename_parts) < 2:
            return CommandResult(
                error=True, message="Usage: /session rename <id_or_name> <new_name>"
            )
        query, new_name = rename_parts[0], rename_parts[1].strip()
        found = ctx.session_manager.find_by_name_or_id(query)
        if found is None:
            return CommandResult(error=True, message=f"Session '{query}' not found.")
        found.name = new_name
        ctx.session_manager.save(found)
        return CommandResult(message=f"Session renamed to '{new_name}'.")

    return CommandResult(
        error=True,
        message=f"Unknown sub-command '{sub}'. Use: save, load, list, delete, rename",
    )


async def _file(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    if not args:
        return CommandResult(error=True, message="Usage: /file <path>")
    try:
        att = read_text_file(args.strip())
    except FileError as exc:
        return CommandResult(error=True, message=exc.user_message)
    state.pending_attachments.append(att)
    size_kb = att.size_bytes / 1024
    return CommandResult(message=f"Attached: {att.filename} ({size_kb:.1f} KB, text)")


async def _image(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    if not args:
        return CommandResult(error=True, message="Usage: /image <path>")
    try:
        att = read_image_file(args.strip())
    except FileError as exc:
        return CommandResult(error=True, message=exc.user_message)
    state.pending_attachments.append(att)
    size_kb = att.size_bytes / 1024
    return CommandResult(
        message=f"Attached: {att.filename} ({size_kb:.1f} KB, {att.image_part.mime_type})"
    )


async def _files(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    if not state.pending_attachments:
        return CommandResult(message="No pending attachments.")
    lines = ["Pending attachments:"]
    for att in state.pending_attachments:
        if isinstance(att, TextAttachment):
            lines.append(f"  {att.filename} ({att.size_bytes / 1024:.1f} KB, text)")
        elif isinstance(att, ImageAttachment):
            lines.append(
                f"  {att.filename} ({att.size_bytes / 1024:.1f} KB, {att.image_part.mime_type})"
            )
    return CommandResult(message="\n".join(lines))


async def _plugins(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    parts = args.split(None, 1) if args else []
    sub = parts[0].lower() if parts else "list"
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("", "list"):
        plugins = ctx.plugin_manager.list_plugins()
        if not plugins:
            return CommandResult(message="No plugins installed.")
        lines = ["Installed plugins:"]
        for p in plugins:
            desc = f" — {p.description}" if p.description else ""
            lines.append(f"  {p.name} {p.version}{desc}")
        return CommandResult(message="\n".join(lines))

    if sub == "info":
        if not rest:
            return CommandResult(error=True, message="Usage: /plugins info <name>")
        info = ctx.plugin_manager.get_plugin(rest)
        if info is None:
            return CommandResult(error=True, message=f"Plugin '{rest}' not found.")
        lines = [
            f"Name:        {info.name}",
            f"Version:     {info.version}",
            f"Description: {info.description}",
            f"Author:      {info.author}",
            f"Groups:      {', '.join(info.entry_point_groups)}",
        ]
        if info.homepage:
            lines.append(f"Homepage:    {info.homepage}")
        return CommandResult(message="\n".join(lines))

    if sub == "install":
        if not rest:
            return CommandResult(error=True, message="Usage: /plugins install <package>")
        ok, output = ctx.plugin_manager.install(rest)
        if ok:
            return CommandResult(message=f"Installed '{rest}'. Restart Anythink to load it.")
        return CommandResult(error=True, message=f"Installation failed:\n{output[:500]}")

    if sub == "remove":
        if not rest:
            return CommandResult(error=True, message="Usage: /plugins remove <package>")
        ok, output = ctx.plugin_manager.remove(rest)
        if ok:
            return CommandResult(message=f"Removed '{rest}'. Restart Anythink to apply changes.")
        return CommandResult(error=True, message=f"Removal failed:\n{output[:500]}")

    return CommandResult(
        error=True,
        message=f"Unknown sub-command '{sub}'. Use: list, info, install, remove",
    )


async def _search(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    if not args:
        return CommandResult(error=True, message="Usage: /search on|off|<query>")

    sub = args.strip().lower()

    if sub == "on":
        state.search_enabled = True
        return CommandResult(message="Web search enabled for this session.")

    if sub == "off":
        state.search_enabled = False
        return CommandResult(message="Web search disabled.")

    # One-off search with the full args as query
    query = args.strip()
    backend = ctx.search_registry.get_available(preferred=ctx.config.search_provider)
    if backend is None:
        return CommandResult(
            error=True,
            message="No search backend available. Install one with: pip install anythink[search]",
        )

    try:
        results = await backend.search(query)
    except SearchError as exc:
        return CommandResult(error=True, message=exc.user_message)

    if not results:
        return CommandResult(message=f"No results found for '{query}'.")

    lines = [f"Search results for '{query}':"]
    for i, r in enumerate(results, 1):
        lines.append(f"  {i}. {r.title}")
        lines.append(f"     {r.url}")
        if r.snippet:
            lines.append(f"     {r.snippet[:120]}")
    return CommandResult(message="\n".join(lines))


async def _exit_cmd(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    return CommandResult(should_exit=True, message="Goodbye!")


# ── Phase 2: rename, undo, bookmark ───────────────────────────────────────────


async def _rename(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    name = args.strip()
    if not name:
        return CommandResult(error=True, message="Usage: /rename <new name>")
    state.session_name = name
    return CommandResult(message=f'Session renamed to "{name}".')


async def _undo(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Signal the TUI to initiate the undo confirmation flow."""
    non_system = [m for m in state.history if m.role != "system"]
    if len(non_system) < 2:
        return CommandResult(error=True, message="Nothing to undo.")

    last_asst = non_system[-1]
    last_user = non_system[-2]
    if last_asst.role != "assistant" or last_user.role != "user":
        return CommandResult(error=True, message="Last exchange is incomplete; cannot undo.")

    u_prev = str(last_user.content)[:60]
    a_prev = str(last_asst.content)[:60]
    msg = (
        "Undo last exchange?\n"
        f"  Your message: {u_prev!r}\n"
        f"  AI response:  {a_prev!r}\n"
        "Type 'y' to confirm."
    )
    return CommandResult(message=msg, action="undo_request")


async def _bookmark(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    bm_mgr = BookmarkManager(state.bookmarks)
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    # /bookmark export [path]
    if sub == "export":
        out_path = Path(rest) if rest else Path("bookmarks_export.txt")
        try:
            bm_mgr.export_text(state.history, out_path, state.session_name)
        except OSError as e:
            return CommandResult(error=True, message=f"Export failed: {e}")
        return CommandResult(message=f"Bookmarks exported to '{out_path}'.")

    # /bookmark search <query>
    if sub == "search":
        if not rest:
            return CommandResult(error=True, message="Usage: /bookmark search <query>")
        try:
            all_sessions = ctx.session_manager.list_sessions()
        except Exception:
            all_sessions = []
        results = BookmarkManager.search_sessions(all_sessions, rest)
        if not results:
            return CommandResult(message=f"No bookmarks matching '{rest}'.")
        lines = [f"Bookmarks matching '{rest}':"]
        for session, bm in results:
            s_name = getattr(session, "name", "") or getattr(session, "id", "?")[:8]
            lines.append(f"  Session: {s_name}  Turn {bm.turn_index}  {bm.label}")
        return CommandResult(message="\n".join(lines))

    # /bookmark label <n> "<text>"
    if sub == "label":
        try:
            parts = shlex.split(rest)
        except ValueError:
            parts = rest.split(None, 1)
        if len(parts) < 2:
            return CommandResult(error=True, message="Usage: /bookmark label <n> <text>")
        try:
            pos = int(parts[0])
        except ValueError:
            return CommandResult(error=True, message="Position must be an integer.")
        label = parts[1]
        if bm_mgr.set_label(pos, label):
            return CommandResult(message=f"Bookmark #{pos} labelled: {label!r}")
        return CommandResult(error=True, message=f"No bookmark at position {pos}.")

    # /bookmark jump <n>
    if sub == "jump":
        try:
            pos = int(rest)
        except ValueError:
            return CommandResult(error=True, message="Usage: /bookmark jump <n>")
        found_bm = bm_mgr.get_by_position(pos)
        if found_bm is None:
            return CommandResult(error=True, message=f"No bookmark at position {pos}.")
        return CommandResult(message=f"Bookmark #{pos} is at turn {found_bm.turn_index}.")

    # /bookmark  or  /bookmark <turn_number>
    # Determine the target turn index
    if sub.isdigit():
        turn_index = int(sub) - 1  # 1-based user input → 0-based index
    else:
        # Default: most recent assistant message
        asst_indices = [i for i, m in enumerate(state.history) if m.role == "assistant"]
        if not asst_indices:
            return CommandResult(error=True, message="No AI responses to bookmark yet.")
        turn_index = asst_indices[-1]

    bm_obj = bm_mgr.add(turn_index)
    return CommandResult(message=f"Bookmarked turn {bm_obj.turn_index + 1}.")


async def _bookmarks(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    bm_mgr = BookmarkManager(state.bookmarks)
    all_bm = bm_mgr.list_all()
    if not all_bm:
        return CommandResult(message="No bookmarks in this session yet.")

    lines = [f"Bookmarks — \"{state.session_name or 'unnamed'}\"", ""]
    lines.append(f"  {'#':<4} {'Turn':<6} {'Label':<30} Time")
    lines.append("  " + "─" * 52)
    for i, bm in enumerate(all_bm, 1):
        label = bm.label[:28] if bm.label else "(unlabeled)"
        ts = bm.created_at.strftime("%H:%M")
        lines.append(f"  {i:<4} {bm.turn_index + 1:<6} {label:<30} {ts}")
    lines.append("")
    lines.append("  Use /bookmark jump <n> to navigate to a bookmark.")
    return CommandResult(message="\n".join(lines))


# ── Phase 3: branch command ────────────────────────────────────────────────────


async def _branch(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Create a branch, list branches, or switch to a named branch."""
    bm = BranchManager(state)
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    # /branch list
    if sub == "list":
        rows = bm.list_branches()
        if not rows:
            return CommandResult(message="No branches (only main).")
        header = f"  {'Branch':<16} {'From turn':<12} {'Messages':<10} Status"
        divider = "  " + "─" * 48
        lines = [f"Branches — \"{state.session_name or 'unnamed'}\"", header, divider]
        for row in rows:
            current = "← current" if row["is_current"] else ""
            lines.append(
                f"  {str(row['name']):<16} {str(row['diverge_turn']):<12}"
                f" {str(row['message_count']):<10} {current}"
            )
        lines.append("")
        lines.append("  /branch switch <name>  to navigate")
        return CommandResult(message="\n".join(lines))

    # /branch switch <name>
    if sub == "switch":
        if not rest:
            return CommandResult(error=True, message="Usage: /branch switch <name>")
        if rest not in state.branches:
            available = ", ".join(state.branches)
            return CommandResult(
                error=True,
                message=f"Branch '{rest}' not found.  Available: {available}",
            )
        return CommandResult(
            message=f"Switching to {rest}…",
            action=f"branch_switch:{rest}",
        )

    # /branch (create) — no args or just create
    if sub in ("", "create", "new"):
        diverge_turn = len([m for m in state.history if m.role != "system"])
        branch_num = len(state.branches)
        new_name = f"Branch {branch_num}"
        msg = (
            f"Create branch from Turn {diverge_turn} (current point)?\n"
            f"  Active branches: {', '.join(state.branches)}\n"
            f"  New branch will be: {new_name!r}\n"
            "Type 'y' to confirm."
        )
        return CommandResult(message=msg, action="branch_confirm")

    return CommandResult(
        error=True,
        message="Usage: /branch  |  /branch list  |  /branch switch <name>",
    )


# ── Phase 4: RAG command ───────────────────────────────────────────────────────


async def _rag(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Manage RAG indexes: list, create, use, off, rebuild, info, delete, status."""
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else "status"
    rest = parts[1].strip() if len(parts) > 1 else ""
    rm = ctx.rag_manager

    # /rag status
    if sub in ("status", ""):
        if rm.is_active:
            name = rm.active_name or "?"
            info = rm.get_info(name)
            msg = f"Active RAG index: {name!r}"
            if info:
                msg += f" ({info.chunk_count:,} chunks, {info.file_count} files)"
        else:
            msg = "No RAG index active. Use /rag use <name> to activate one."
        return CommandResult(message=msg)

    # /rag list
    if sub == "list":
        indexes = rm.list_indexes()
        if not indexes:
            return CommandResult(message="No RAG indexes defined. Use /rag new to create one.")
        lines = [f"  {'Name':<20} {'Type':<12} {'Chunks':<8} Last indexed"]
        lines.append("  " + "─" * 60)
        for idx in indexes:
            last = idx.last_indexed.strftime("%Y-%m-%d") if idx.last_indexed else "never"
            marker = " ←" if rm.active_name == idx.name else ""
            lines.append(
                f"  {idx.name:<20} {idx.index_type:<12} {idx.chunk_count:<8} {last}{marker}"
            )
        return CommandResult(message="\n".join(lines))

    # /rag info <name>
    if sub == "info":
        name = rest or rm.active_name or ""
        if not name:
            return CommandResult(error=True, message="Usage: /rag info <name>")
        info = rm.get_info(name)
        if info is None:
            return CommandResult(error=True, message=f"No index named '{name}'.")
        last = info.last_indexed.strftime("%Y-%m-%d %H:%M") if info.last_indexed else "never"
        lines = [
            f"Name:        {info.name}",
            f"Type:        {info.index_type}",
            f"Source:      {info.source_path}",
            f"Persistence: {info.persistence_mode}",
            f"Embeddings:  {info.embedding_backend}",
            f"Files:       {info.file_count}",
            f"Chunks:      {info.chunk_count:,}",
            f"Last built:  {last}",
        ]
        return CommandResult(message="\n".join(lines))

    # /rag use <name>
    if sub == "use":
        if not rest:
            return CommandResult(error=True, message="Usage: /rag use <name>")
        if rm.use_index(rest):
            # Persist active index in config
            from dataclasses import replace

            new_config = replace(ctx.config, active_rag_index=rest)
            ctx.config_manager.save(new_config)
            return CommandResult(
                message=f"RAG index '{rest}' is now active.",
                action="rag_hud_update",
            )
        return CommandResult(error=True, message=f"Index '{rest}' not found.")

    # /rag off
    if sub == "off":
        rm.deactivate()
        from dataclasses import replace

        new_config = replace(ctx.config, active_rag_index=None)
        ctx.config_manager.save(new_config)
        return CommandResult(message="RAG deactivated.", action="rag_hud_update")

    # /rag delete <name>
    if sub == "delete":
        if not rest:
            return CommandResult(error=True, message="Usage: /rag delete <name>")
        try:
            rm.delete_index(rest)
        except Exception as e:
            return CommandResult(error=True, message=str(e))
        return CommandResult(message=f"Index '{rest}' deleted.")

    # /rag new <name> — interactive creation shortcut
    if sub == "new":
        if not rest:
            return CommandResult(error=True, message="Usage: /rag new <name>")
        # Use defaults; a future interactive wizard can be added
        return CommandResult(
            message=(
                f"To create index '{rest}' interactively, use:\n"
                f"  /rag new {rest} project|document <source-path> rebuild|persist\n"
                "Example: /rag new my-code project /home/user/project rebuild"
            ),
            action="rag_new_request",
        )

    # /rag new <name> <type> <path> <mode>
    if sub == "new" or (sub and " " in (args or "")):
        # Already handled above; fall through to rebuild check
        pass

    # /rag rebuild <name>
    if sub == "rebuild":
        name = rest or rm.active_name or ""
        if not name:
            return CommandResult(error=True, message="Usage: /rag rebuild <name>")
        return CommandResult(
            message=f"Rebuilding '{name}'…  (this may take a moment)",
            action=f"rag_rebuild:{name}",
        )

    return CommandResult(
        error=True,
        message="Usage: /rag list|new|use|off|rebuild|info|delete|status",
    )


# ── Phase 5: exec, browse commands ────────────────────────────────────────────


async def _exec(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Run code via local PATH runtime, or change the exec approval mode."""
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    if not sub:
        return CommandResult(
            error=True,
            message=(
                "Usage: /exec <language> <code>  |  /exec mode ask|auto\n"
                f"Languages: {', '.join(sorted(set(RUNTIMES.keys())))}"
            ),
        )

    if sub == "mode":
        if rest not in ("ask", "auto"):
            return CommandResult(error=True, message="Usage: /exec mode ask|auto")
        from dataclasses import replace

        new_config = replace(ctx.config, exec_mode=rest)
        ctx.config_manager.save(new_config)
        ctx.config = new_config
        return CommandResult(message=f"Code execution mode set to '{rest}'.")

    # /exec <language> <code>
    lang = sub
    code = rest
    if not code:
        return CommandResult(
            error=True,
            message=(f"Usage: /exec {lang} <code>\n" "Example: /exec python print('hello')"),
        )

    if lang not in RUNTIMES:
        valid = ", ".join(sorted(set(RUNTIMES.keys())))
        return CommandResult(
            error=True,
            message=f"Unknown language '{lang}'. Supported: {valid}",
        )

    return CommandResult(
        message=f"Run {lang} code:\n```{lang}\n{code}\n```\nType 'y' to confirm.",
        action="exec_request",
        extra={"language": lang, "code": code},
    )


async def _browse(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Fetch a web page or run a snippet search, or change the browse mode."""
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    if not sub:
        return CommandResult(
            error=True,
            message="Usage: /browse <url|query>  |  /browse mode ask|auto|http|headless",
        )

    if sub == "mode":
        valid_modes = ("ask", "auto", "http", "headless")
        if rest not in valid_modes:
            return CommandResult(
                error=True,
                message=f"Usage: /browse mode {'|'.join(valid_modes)}",
            )
        from dataclasses import replace

        if rest in ("ask", "auto"):
            new_config = replace(ctx.config, browse_autonomy=rest)
        else:
            new_config = replace(ctx.config, browse_mode=rest)
        ctx.config_manager.save(new_config)
        ctx.config = new_config
        return CommandResult(message=f"Browse mode set to '{rest}'.")

    # /browse <url_or_query>
    target = args.strip()
    is_url = target.startswith(("http://", "https://"))
    extra: dict[str, str] = {"url": target, "query": ""} if is_url else {"url": "", "query": target}
    prompt = f"Fetch {target}?" if is_url else f"Search web for: {target!r}?"

    return CommandResult(
        message=f"{prompt} Type 'y' to confirm.",
        action="browse_request",
        extra=extra,
    )


# ── Phase 6: MCP command ───────────────────────────────────────────────────────


async def _mcp(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Manage MCP servers (list, connect, disconnect, call tools, server control)."""
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else "status"
    rest = parts[1].strip() if len(parts) > 1 else ""
    mgr = ctx.mcp_manager

    # /mcp status
    if sub in ("status", ""):
        servers = mgr.list_servers()
        tools = mgr.list_tools()
        lines = [
            f"MCP status: {len(servers)} server(s), {len(tools)} tool(s)",
        ]
        if servers:
            for s in servers:
                marker = "●" if s.connected else "○"
                lines.append(f"  {marker} {s.name} [{s.kind}] — {s.tool_count} tool(s)")
        else:
            lines.append("  No servers registered.")
        return CommandResult(message="\n".join(lines))

    # /mcp list
    if sub == "list":
        servers = mgr.list_servers()
        if not servers:
            return CommandResult(message="No MCP servers registered.")
        lines = [f"  {'Name':<16} {'Kind':<10} {'Transport':<10} {'Tools':<6} Status"]
        lines.append("  " + "─" * 54)
        for s in servers:
            conn = "connected" if s.connected else "offline"
            lines.append(f"  {s.name:<16} {s.kind:<10} {s.transport:<10} {s.tool_count:<6} {conn}")
        return CommandResult(message="\n".join(lines))

    # /mcp tools
    if sub == "tools":
        tools = mgr.list_tools()
        if not tools:
            return CommandResult(message="No MCP tools available.")
        lines = [f"  {'Tool':<24} {'Server':<16} Description"]
        lines.append("  " + "─" * 64)
        for t in tools:
            desc = t.description[:36] + "…" if len(t.description) > 36 else t.description
            lines.append(f"  {t.name:<24} {t.server_name:<16} {desc}")
        return CommandResult(message="\n".join(lines))

    # /mcp connect <name> <transport> <command_or_url>
    if sub == "connect":
        conn_parts = rest.split(None, 2)
        if len(conn_parts) < 3:
            return CommandResult(
                error=True,
                message=(
                    "Usage: /mcp connect <name> stdio <command>"
                    "  |  /mcp connect <name> sse <url>"
                ),
            )
        name, transport, target = conn_parts[0], conn_parts[1].lower(), conn_parts[2]
        command = target if transport == "stdio" else ""
        url = target if transport == "sse" else ""
        config = MCPConnectConfig(name=name, transport=transport, command=command, url=url)
        try:
            await mgr.connect(config)
        except MCPError as exc:
            return CommandResult(error=True, message=exc.user_message)
        except Exception as exc:
            return CommandResult(error=True, message=f"Connection failed: {exc}")
        tool_count = mgr._externals[name].tool_count if name in mgr._externals else 0
        return CommandResult(message=f"Connected to '{name}' ({tool_count} tool(s) discovered).")

    # /mcp disconnect <name>
    if sub == "disconnect":
        if not rest:
            return CommandResult(error=True, message="Usage: /mcp disconnect <name>")
        try:
            await mgr.disconnect(rest)
        except MCPError as exc:
            return CommandResult(error=True, message=exc.user_message)
        return CommandResult(message=f"Disconnected from '{rest}'.")

    # /mcp call <tool> [key=value ...]
    if sub == "call":
        call_parts = rest.split(None, 1)
        if not call_parts:
            return CommandResult(error=True, message="Usage: /mcp call <tool> [key=value ...]")
        tool_name = call_parts[0]
        arg_str = call_parts[1] if len(call_parts) > 1 else ""
        arguments: dict[str, str] = {}
        if arg_str:
            for token in shlex.split(arg_str):
                if "=" in token:
                    k, _, v = token.partition("=")
                    arguments[k.strip()] = v.strip()
        return CommandResult(
            message=f"Call MCP tool '{tool_name}'? Type 'y' to confirm.",
            action="mcp_call_request",
            extra={"tool": tool_name, **arguments},
        )

    # /mcp server <start|stop|status>
    if sub == "server":
        server_parts = rest.split(None, 1)
        server_sub = server_parts[0].lower() if server_parts else "status"

        if server_sub == "status":
            from anythink.mcp.server import AnythinkMCPServer

            # Check if there's an existing server tracked on ctx (we piggy-back via extra)
            return CommandResult(message="MCP server: not running (use /mcp server start).")

        if server_sub == "start":
            from anythink.mcp.server import AnythinkMCPServer

            srv = AnythinkMCPServer(mgr)
            try:
                address = await srv.start()
            except MCPError as exc:
                return CommandResult(error=True, message=exc.user_message)
            return CommandResult(
                message=f"Anythink MCP server started at {address}",
                action="mcp_server_started",
                extra={"address": address},
            )

        if server_sub == "stop":
            return CommandResult(message="MCP server stopped.")

        return CommandResult(
            error=True,
            message="Usage: /mcp server start|stop|status",
        )

    return CommandResult(
        error=True,
        message="Usage: /mcp list|tools|connect|disconnect|status|call|server",
    )


# ── Phase 8: voice, notify commands ───────────────────────────────────────────


async def _voice(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Start voice capture or change the Whisper model."""
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub == "model":
        model = rest.lower()
        valid = ", ".join(sorted(VALID_MODELS))
        if model not in VALID_MODELS:
            return CommandResult(error=True, message=f"Unknown model '{model}'. Valid: {valid}")
        from dataclasses import replace

        new_config = replace(ctx.config, voice_model=model)
        ctx.config_manager.save(new_config)
        ctx.config = new_config
        return CommandResult(message=f"Voice model set to '{model}'.")

    if sub == "language":
        lang = rest.strip() or None
        from dataclasses import replace

        new_config = replace(ctx.config, voice_language=lang)
        ctx.config_manager.save(new_config)
        ctx.config = new_config
        return CommandResult(
            message=f"Voice language set to '{lang or 'auto-detect'}'.",
        )

    # /voice — start recording
    return CommandResult(
        message=(
            f"🎙 Recording… (model: {ctx.config.voice_model}"
            f"{', lang: ' + (ctx.config.voice_language or 'auto') if True else ''})\n"
            "Press Enter to stop and transcribe."
        ),
        action="voice_request",
    )


async def _notify(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Enable/disable desktop notifications, or adjust per-type settings."""
    parts = args.strip().split(None, 2)
    sub = parts[0].lower() if parts else "status"

    notifier = ctx.notifier

    if sub in ("status", ""):
        snap = notifier.status()
        global_state = "on" if snap["enabled"] else "off"
        lines = [
            f"Notifications: {global_state}  (backend: {snap['backend']})",
            f"  Slow-response threshold: {SLOW_RESPONSE_S:.0f}s",
            f"  Slow-exec threshold:     {SLOW_EXEC_S:.0f}s",
            "",
            "  Per-type settings:",
        ]
        for key in NOTIFICATION_DEFAULTS:
            flag = snap.get(f"type:{key}", True)
            lines.append(f"    {key:<22} {'on' if flag else 'off'}")
        return CommandResult(message="\n".join(lines))

    if sub == "on":
        notifier.set_enabled(True)
        from dataclasses import replace

        ctx.config = replace(ctx.config, notifications={"_global": True})
        return CommandResult(message="Desktop notifications enabled.")

    if sub == "off":
        notifier.set_enabled(False)
        from dataclasses import replace

        ctx.config = replace(ctx.config, notifications={"_global": False})
        return CommandResult(message="Desktop notifications disabled.")

    if sub == "type":
        if len(parts) < 3:
            return CommandResult(
                error=True,
                message=(
                    "Usage: /notify type <name> on|off\n"
                    f"Types: {', '.join(NOTIFICATION_DEFAULTS)}"
                ),
            )
        type_name = parts[1].lower()
        flag_str = parts[2].lower()
        if type_name not in NOTIFICATION_DEFAULTS:
            return CommandResult(
                error=True,
                message=f"Unknown type '{type_name}'. Valid: {', '.join(NOTIFICATION_DEFAULTS)}",
            )
        if flag_str not in ("on", "off"):
            return CommandResult(error=True, message="Usage: /notify type <name> on|off")
        enabled = flag_str == "on"
        notifier.set_type_enabled(type_name, enabled)
        return CommandResult(message=f"Notification '{type_name}' set to '{flag_str}'.")

    return CommandResult(
        error=True,
        message="Usage: /notify on|off|status  |  /notify type <name> on|off",
    )


async def _settings_cmd(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    return CommandResult(action="open_settings")


# ── V3: Per-model generation parameters ───────────────────────────────────────


async def _params(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """View or update generation parameters for the active model alias."""
    from dataclasses import replace as dc_replace

    from anythink.providers.base import GenerationParams

    alias_name = ctx.config.default_model_alias
    alias = ctx.model_registry.get(alias_name or "") if alias_name else None

    if not alias:
        return CommandResult(
            error=True,
            message="No active model alias. Set one with 'anythink model add'.",
        )

    if not args.strip():
        p = alias.gen_params
        if p is None:
            return CommandResult(
                message=f"  {alias.alias}: using provider defaults (no custom params set)"
            )
        lines = [f"  Generation params for '{alias.alias}':"]
        lines.append(f"    temperature      = {p.temperature}")
        lines.append(f"    max_tokens       = {p.max_tokens}")
        lines.append(f"    top_p            = {p.top_p}")
        lines.append(f"    frequency_penalty= {p.frequency_penalty}")
        lines.append(f"    presence_penalty = {p.presence_penalty}")
        return CommandResult(message="\n".join(lines))

    if args.strip().lower() == "reset":
        updated = dc_replace(alias, gen_params=None)
        ctx.model_registry.add(updated)
        return CommandResult(message=f"  Params for '{alias.alias}' reset to provider defaults.")

    # Parse key=value pairs
    current = alias.gen_params or GenerationParams()
    temp = current.temperature
    max_tok = current.max_tokens
    top_p = current.top_p
    freq_pen = current.frequency_penalty
    pres_pen = current.presence_penalty

    for token in args.split():
        if "=" not in token:
            continue
        key, _, val_str = token.partition("=")
        key = key.strip().lower()
        try:
            float(val_str)  # validate it's numeric before branching
            if key == "temperature":
                temp = float(val_str)
            elif key == "max_tokens":
                max_tok = int(float(val_str))
            elif key == "top_p":
                top_p = float(val_str)
            elif key == "frequency_penalty":
                freq_pen = float(val_str)
            elif key == "presence_penalty":
                pres_pen = float(val_str)
            else:
                return CommandResult(
                    error=True,
                    message=(
                        f"Unknown param '{key}'. Valid: temperature, max_tokens,"
                        " top_p, frequency_penalty, presence_penalty"
                    ),
                )
        except ValueError:
            return CommandResult(error=True, message=f"Invalid value for '{key}': {val_str}")

    new_params = GenerationParams(
        temperature=temp,
        max_tokens=max_tok,
        top_p=top_p,
        frequency_penalty=freq_pen,
        presence_penalty=pres_pen,
    )
    updated = dc_replace(alias, gen_params=new_params)
    ctx.model_registry.add(updated)
    return CommandResult(message=f"  Params updated for '{alias.alias}'.\n  Use /params to review.")


# ── V3: Spend tracking ─────────────────────────────────────────────────────────


async def _cost(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Show estimated API spend for the session or historical totals."""
    sub = args.strip().lower()

    tracker = ctx.spend_tracker

    if sub in ("", "session"):
        total = tracker.session_total(state.session_id)
        return CommandResult(
            message=f"  Session spend (estimate): ${total:.4f}\n  (Actual billing may differ.)"
        )

    if sub == "today":
        total = tracker.daily_total()
        return CommandResult(message=f"  Today's spend (estimate): ${total:.4f}")

    if sub == "month":
        total = tracker.monthly_total()
        return CommandResult(message=f"  This month's spend (estimate): ${total:.4f}")

    if sub == "by-model":
        by_model = tracker.by_model()
        if not by_model:
            return CommandResult(message="  No spend data recorded yet.")
        lines = ["  Spend by model (estimate):"]
        for model_id, amt in sorted(by_model.items(), key=lambda x: -x[1]):
            lines.append(f"    {model_id:<40} ${amt:.4f}")
        return CommandResult(message="\n".join(lines))

    if sub == "by-provider":
        by_prov = tracker.by_provider()
        if not by_prov:
            return CommandResult(message="  No spend data recorded yet.")
        lines = ["  Spend by provider (estimate):"]
        for prov, amt in sorted(by_prov.items(), key=lambda x: -x[1]):
            lines.append(f"    {prov:<20} ${amt:.4f}")
        return CommandResult(message="\n".join(lines))

    return CommandResult(
        error=True,
        message="Usage: /cost  |  /cost today  |  /cost month  |  /cost by-model  |  /cost by-provider",  # noqa: E501
    )


# ── V3: Prompt templates ───────────────────────────────────────────────────────


async def _template(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Manage saved prompt templates."""
    from anythink.config.templates import PromptTemplate

    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else "list"
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub == "list":
        templates = ctx.template_manager.list_all()
        if not templates:
            return CommandResult(
                message="  No templates saved. Use /template save <name> <body> to create one."
            )
        lines = ["  Saved templates:"]
        for t in templates:
            desc = f" — {t.description}" if t.description else ""
            vars_str = f" [{', '.join(t.variables())}]" if t.variables() else ""
            lines.append(f"    {t.name}{vars_str}{desc}")
        return CommandResult(message="\n".join(lines))

    if sub == "show":
        if not rest:
            return CommandResult(error=True, message="Usage: /template show <name>")
        t_show = ctx.template_manager.get(rest)
        if t_show is None:
            return CommandResult(error=True, message=f"  Template '{rest}' not found.")
        t = t_show
        lines = [f"  Template: {t.name}"]
        if t.description:
            lines.append(f"  Description: {t.description}")
        if t.variables():
            lines.append(f"  Variables: {', '.join(t.variables())}")
        lines.append(f"  Body:\n{t.body}")
        return CommandResult(message="\n".join(lines))

    if sub == "delete":
        if not rest:
            return CommandResult(error=True, message="Usage: /template delete <name>")
        try:
            ctx.template_manager.remove(rest)
        except Exception as e:
            return CommandResult(error=True, message=str(e))
        return CommandResult(message=f"  Template '{rest}' deleted.")

    if sub == "save":
        name_and_body = rest.split(None, 1)
        if len(name_and_body) < 2:
            return CommandResult(
                error=True,
                message="Usage: /template save <name> <body text>",
            )
        name = name_and_body[0]
        body = name_and_body[1]
        t = PromptTemplate(name=name, body=body)
        ctx.template_manager.add(t)
        vars_list = t.variables()
        vars_info = f" (variables: {', '.join(vars_list)})" if vars_list else ""
        return CommandResult(message=f"  Template '{name}' saved.{vars_info}")

    return CommandResult(
        error=True,
        message="Usage: /template list  |  save <name> <body>  |  show <name>  |  delete <name>",
    )


async def _use(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Instantiate a prompt template and queue it to be sent as a user message."""
    parts = args.strip().split(None, 1)
    if not parts or not parts[0]:
        return CommandResult(error=True, message="Usage: /use <template-name> [key=value ...]")

    name = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    tmpl = ctx.template_manager.get(name)
    if tmpl is None:
        return CommandResult(
            error=True, message=f"  Template '{name}' not found. Use /template list."
        )

    # Parse key=value pairs
    variables: dict[str, str] = {}
    for token in rest.split():
        if "=" in token:
            k, _, v = token.partition("=")
            variables[k.strip()] = v.strip()

    try:
        rendered = tmpl.render(variables)
    except Exception as e:
        return CommandResult(error=True, message=str(e))

    return CommandResult(
        action="template_send",
        extra={"rendered": rendered},
        message=f"  Using template '{name}'…",
    )


# ── V3: Diagnostics ────────────────────────────────────────────────────────────


async def _doctor(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Run a comprehensive health check of the Anythink installation."""
    from anythink.diagnostics import run_diagnostics

    results = await run_diagnostics(ctx)

    lines = ["  Anythink Diagnostics", "  " + "─" * 50]
    current_category = ""
    pass_count = warn_count = fail_count = 0

    for r in results:
        if r.category != current_category:
            current_category = r.category
            lines.append(f"\n  {r.category.title()}")

        icon = {"ok": "✓", "warn": "⚠", "fail": "❌"}.get(r.status, "?")
        lines.append(f"    {icon} {r.name}: {r.message}")
        if r.detail:
            lines.append(f"      → {r.detail}")

        if r.status == "ok":
            pass_count += 1
        elif r.status == "warn":
            warn_count += 1
        else:
            fail_count += 1

    lines.append(f"\n  Summary: {pass_count} passed, {warn_count} warnings, {fail_count} failed")
    return CommandResult(message="\n".join(lines))


# ── V3: Self-update ────────────────────────────────────────────────────────────


async def _update(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Check for Anythink updates or initiate an upgrade."""
    from anythink.updater import check_update

    sub = args.strip().lower()

    current, latest = await check_update()

    if sub == "check" or not latest:
        if latest is None:
            return CommandResult(message=f"  Current version: {current}  (Could not reach PyPI.)")
        if latest == current:
            return CommandResult(message=f"  Anythink is up to date ({current}).")
        return CommandResult(
            message=f"  Current: {current}  →  Available: {latest}\n  Run /update to upgrade."
        )

    # /update (no args) — offer upgrade
    if latest == current:
        return CommandResult(message=f"  Anythink is already up to date ({current}).")

    return CommandResult(
        action="update_confirm",
        extra={"current": current, "latest": latest},
        message=(
            f"  Upgrade available: {current} → {latest}\n" "  Type 'y' to confirm the upgrade."
        ),
    )


# ── V3: Config backup / restore ────────────────────────────────────────────────


async def _config_cmd(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Export or import Anythink configuration as a portable bundle."""
    from anythink.config.backup import export_config, import_config

    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub == "export":
        if rest:
            out_path = Path(rest)
        else:
            from datetime import datetime as _dt

            stamp = _dt.utcnow().strftime("%Y-%m-%d")
            out_path = ctx.paths.data_dir / f"anythink-backup-{stamp}.json"
        try:
            export_config(ctx, out_path)
        except Exception as e:
            return CommandResult(error=True, message=f"  Export failed: {e}")
        return CommandResult(
            message=(
                f"  Config exported to: {out_path}\n"
                "  Included: theme, models, personas, templates, schedules\n"
                "  Excluded: API keys (re-enter with 'anythink keys add' on the new machine)"
            )
        )

    if sub == "import":
        if not rest:
            return CommandResult(error=True, message="Usage: /config import <path>")
        in_path = Path(rest)
        if not in_path.exists():
            return CommandResult(error=True, message=f"  File not found: {rest}")
        try:
            import_config(ctx, in_path)
        except Exception as e:
            return CommandResult(error=True, message=f"  Import failed: {e}")
        return CommandResult(
            message=(
                "  Config imported successfully.\n"
                "  Restart Anythink for all changes to take effect."
            )
        )

    if sub == "validate":
        from anythink.config.validator import ConfigValidator, format_validation_table

        issues = ConfigValidator().validate(ctx)
        return CommandResult(message=format_validation_table(issues), action="debug_display")

    return CommandResult(
        error=True,
        message="Usage: /config export [path]  |  /config import <path>  |  /config validate",
    )


# ── V3: Session export ─────────────────────────────────────────────────────────


async def _export(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Export the current session to Markdown, JSON, or PDF."""
    from anythink.app.chat import _build_session
    from anythink.export.formats import export_json, export_markdown, export_pdf

    tokens = args.strip().split() if args.strip() else []
    fmt = "markdown"
    out_path: Path | None = None
    message_range: tuple[int, int] | None = None

    i = 0
    while i < len(tokens):
        tok = tokens[i].lower()
        if tok in ("markdown", "md"):
            fmt = "markdown"
        elif tok == "json":
            fmt = "json"
        elif tok == "pdf":
            fmt = "pdf"
        elif tok == "--range" and i + 1 < len(tokens):
            i += 1
            try:
                start_s, end_s = tokens[i].split("-")
                message_range = (int(start_s) - 1, int(end_s))
            except ValueError:
                return CommandResult(error=True, message="Usage: --range N-M (e.g. --range 1-10)")
        elif not tok.startswith("-"):
            out_path = Path(tok)
        i += 1

    ext_map = {"markdown": "md", "json": "json", "pdf": "pdf"}
    if out_path is None:
        ctx.paths.exports_dir.mkdir(parents=True, exist_ok=True)
        out_path = ctx.paths.exports_dir / f"{state.session_id}.{ext_map[fmt]}"

    session = _build_session(state)
    try:
        if fmt == "markdown":
            export_markdown(session, out_path, message_range=message_range)
        elif fmt == "json":
            export_json(session, out_path, message_range=message_range)
        else:
            export_pdf(session, out_path, message_range=message_range)
    except Exception as e:
        return CommandResult(error=True, message=f"  Export failed: {e}")

    return CommandResult(message=f"  Exported {fmt} to: {out_path}")


# ── V3: Multi-model comparison ─────────────────────────────────────────────────


async def _compare(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Set up a multi-model comparison for the next message."""
    parts = args.strip().split()

    if not parts:
        return CommandResult(
            error=True,
            message="Usage: /compare <alias1> <alias2> [alias3 ...]",
        )

    # Validate aliases exist
    missing = [a for a in parts if not ctx.model_registry.exists(a)]
    if missing:
        return CommandResult(
            error=True,
            message=f"  Unknown alias(es): {', '.join(missing)}. Use 'anythink model list'.",
        )

    if len(parts) < 2:
        return CommandResult(
            error=True,
            message="  Comparison requires at least 2 model aliases.",
        )

    return CommandResult(
        action="compare_request",
        extra={"aliases": parts},
        message=(
            f"  Comparison mode set for: {', '.join(parts)}\n"
            "  Send your next message to compare."
        ),
    )


# ── V3: Scheduled prompts ──────────────────────────────────────────────────────


async def _schedule(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Manage scheduled prompt automation."""
    from anythink.schedule.models import ScheduledPrompt

    parts = args.strip().split(None, 3)
    sub = parts[0].lower() if parts else "list"

    if sub == "list":
        schedules = ctx.schedule_manager.list_all()
        if not schedules:
            return CommandResult(
                message="  No schedules defined. Use /schedule add <name> <cron> <prompt>."
            )
        lines = ["  Scheduled prompts:"]
        for s in schedules:
            status = "enabled" if s.enabled else "paused"
            last = s.last_run.strftime("%Y-%m-%d %H:%M") if s.last_run else "never"
            lines.append(f"    [{status}] {s.name}  cron={s.cron_expr!r}  last_run={last}")
        return CommandResult(message="\n".join(lines))

    if sub == "add":
        # /schedule add <name> <cron> <prompt>
        if len(parts) < 4:
            return CommandResult(
                error=True,
                message='Usage: /schedule add <name> "<cron>" <prompt text>',
            )
        name = parts[1]
        cron_expr = parts[2]
        prompt_text = parts[3]
        s = ScheduledPrompt(name=name, cron_expr=cron_expr, prompt=prompt_text)
        ctx.schedule_manager.add(s)
        return CommandResult(message=f"  Schedule '{name}' added (cron: {cron_expr!r}).")

    if sub in ("remove", "delete"):
        name = parts[1] if len(parts) > 1 else ""
        if not name:
            return CommandResult(error=True, message="Usage: /schedule remove <name>")
        try:
            ctx.schedule_manager.remove(name)
        except Exception as e:
            return CommandResult(error=True, message=str(e))
        return CommandResult(message=f"  Schedule '{name}' removed.")

    if sub == "enable":
        name = parts[1] if len(parts) > 1 else ""
        if not name:
            return CommandResult(error=True, message="Usage: /schedule enable <name>")
        try:
            ctx.schedule_manager.enable(name)
        except Exception as e:
            return CommandResult(error=True, message=str(e))
        return CommandResult(message=f"  Schedule '{name}' enabled.")

    if sub == "disable":
        name = parts[1] if len(parts) > 1 else ""
        if not name:
            return CommandResult(error=True, message="Usage: /schedule disable <name>")
        try:
            ctx.schedule_manager.disable(name)
        except Exception as e:
            return CommandResult(error=True, message=str(e))
        return CommandResult(message=f"  Schedule '{name}' disabled.")

    if sub == "run":
        name = parts[1] if len(parts) > 1 else ""
        if not name:
            return CommandResult(error=True, message="Usage: /schedule run <name>")
        schedule = ctx.schedule_manager.get(name)
        if schedule is None:
            return CommandResult(error=True, message=f"  Schedule '{name}' not found.")
        return CommandResult(
            action="schedule_run",
            extra={"schedule_name": name},
            message=f"  Running schedule '{name}'…",
        )

    return CommandResult(
        error=True,
        message=(
            "Usage: /schedule list  |  add <name> <cron> <prompt>"
            "  |  remove|run|enable|disable <name>"
        ),
    )


# ── V3.2: /preview ────────────────────────────────────────────────────────────


async def _preview(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Show the fully assembled prompt that would be sent without sending it."""
    import time

    from anythink.app.chat import _trim_history  # noqa: PLC0415
    from anythink.debug.formatters import format_prompt_payload  # noqa: PLC0415
    from anythink.debug.models import RequestDebugRecord  # noqa: PLC0415
    from anythink.session.models import _msg_to_dict  # noqa: PLC0415

    trimmed = _trim_history(state.history, state.context_window)
    try:
        payload = [_msg_to_dict(m) for m in trimmed]
    except Exception:
        payload = []

    now = time.monotonic()
    synthetic = RequestDebugRecord(
        request_id=0,
        session_id=state.session_id,
        timestamp=__import__("datetime").datetime.utcnow(),
        model_id=state.model_id,
        provider_name=state.provider.name,
        alias_name=state.model_id,
        prompt_payload=payload,
        gen_params=state.gen_params,
        t_start=now,
        t_prompt_assembled=now,
    )
    return CommandResult(message=format_prompt_payload(synthetic), action="debug_display")


# ── V3.2: /perf alias ─────────────────────────────────────────────────────────


async def _perf_alias(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    """Alias for /debug perf — show session performance summary."""
    dm = ctx.debug_manager
    if not dm.is_active():
        return CommandResult(
            error=True,
            message="Debug mode is not active. Run /debug on first.",
        )
    records = dm.all_records()
    if not records:
        return CommandResult(error=True, message="No debug records yet.")
    from anythink.debug.formatters import format_perf_summary

    return CommandResult(message=format_perf_summary(records), action="debug_display")
