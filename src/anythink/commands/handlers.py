"""Built-in slash command handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anythink.commands.base import CommandResult, SlashCommand
from anythink.exceptions import FileError, SearchError, SessionError
from anythink.files.reader import ImageAttachment, TextAttachment, read_image_file, read_text_file
from anythink.providers.base import ChatMessage
from anythink.session.models import Session

if TYPE_CHECKING:
    from anythink.app.chat import ChatState
    from anythink.app.context import AppContext
    from anythink.commands.registry import CommandRegistry


def register_commands(registry: CommandRegistry) -> None:
    """Register all built-in Anythink slash commands."""
    registry.register(SlashCommand("help", "Show available commands", _help, "/help"))
    registry.register(SlashCommand("clear", "Clear conversation history", _clear, "/clear"))
    registry.register(SlashCommand("history", "Show recent conversation turns", _history, "/history"))
    registry.register(SlashCommand("tokens", "Show context-window token usage", _tokens, "/tokens"))
    registry.register(SlashCommand("model", "Show the active provider and model", _model, "/model"))
    registry.register(SlashCommand("persona", "Set or clear the active persona", _persona, "/persona <name> | clear"))
    registry.register(SlashCommand("session", "Manage saved sessions", _session, "/session <save|load|list|delete|rename>"))
    registry.register(SlashCommand("file", "Attach a text file to the next message", _file, "/file <path>"))
    registry.register(SlashCommand("image", "Attach an image to the next message", _image, "/image <path>"))
    registry.register(SlashCommand("files", "List pending file attachments", _files, "/files"))
    registry.register(SlashCommand("search", "Enable/disable web search or run a one-off search", _search, "/search on|off|<query>"))
    registry.register(SlashCommand("exit", "Exit Anythink", _exit_cmd, "/exit"))
    registry.register(SlashCommand("quit", "Exit Anythink", _exit_cmd, "/quit"))


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
    return CommandResult(
        message=f"Provider: {state.provider.name}  Model: {state.model_id}"
    )


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
        session = ctx.session_manager.find_by_name_or_id(rest)
        if session is None:
            return CommandResult(error=True, message=f"Session '{rest}' not found. Use /session list.")
        state.history = list(session.messages)
        state.session_id = session.id
        state.session_name = session.name
        state.total_tokens_used = 0
        label = session.name or session.id[:8] + "…"
        return CommandResult(message=f"Loaded session '{label}' ({len(session.messages)} messages).")

    if sub == "delete":
        if not rest:
            return CommandResult(error=True, message="Usage: /session delete <id_or_name>")
        session = ctx.session_manager.find_by_name_or_id(rest)
        if session is None:
            return CommandResult(error=True, message=f"Session '{rest}' not found.")
        ctx.session_manager.delete(session.id)
        label = session.name or session.id[:8] + "…"
        return CommandResult(message=f"Session '{label}' deleted.")

    if sub == "rename":
        rename_parts = rest.split(None, 1)
        if len(rename_parts) < 2:
            return CommandResult(error=True, message="Usage: /session rename <id_or_name> <new_name>")
        query, new_name = rename_parts[0], rename_parts[1].strip()
        session = ctx.session_manager.find_by_name_or_id(query)
        if session is None:
            return CommandResult(error=True, message=f"Session '{query}' not found.")
        session.name = new_name
        ctx.session_manager.save(session)
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
    return CommandResult(message=f"Attached: {att.filename} ({size_kb:.1f} KB, {att.image_part.mime_type})")


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
            lines.append(f"  {att.filename} ({att.size_bytes / 1024:.1f} KB, {att.image_part.mime_type})")
    return CommandResult(message="\n".join(lines))


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
