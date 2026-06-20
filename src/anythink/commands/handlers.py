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


async def _help(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    lines = ["Available commands:"]
    for name in registry.names():
        cmd = registry.get(name)
        if cmd is not None:
            lines.append(f"  /{name:<12} {cmd.description}")
    return CommandResult(message="\n".join(lines))


async def _clear(
    ctx: AppContext,
    args: str,
    state: ChatState,
    registry: CommandRegistry,
) -> CommandResult:
    state.history = [m for m in state.history if m.role == "system"]
    state.total_tokens_used = 0
    return CommandResult(message="Conversation cleared.")


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
