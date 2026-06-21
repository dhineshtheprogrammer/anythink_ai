"""Interactive chat loop orchestrator."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from rich.text import Text

from anythink import __version__
from anythink.app.context import AppContext
from anythink.bookmarks.models import Bookmark
from anythink.branch.models import BranchInfo
from anythink.commands.registry import CommandRegistry
from anythink.config.models import ModelAlias
from anythink.exceptions import AnythinkError, SearchError
from anythink.files.reader import FileAttachment, ImageAttachment, TextAttachment
from anythink.providers.base import (
    BaseProvider,
    ChatMessage,
    ContentPart,
    GenerationParams,
    TextPart,
)
from anythink.search.base import SearchResult
from anythink.session.models import Session
from anythink.ui.banner import print_banner
from anythink.ui.input import make_prompt_session
from anythink.ui.renderer import StreamRenderer
from anythink.ui.status import ContextStatusBar


@dataclass
class ChatState:
    """Mutable per-session chat state."""

    provider: BaseProvider
    model_id: str
    context_window: int
    history: list[ChatMessage] = field(default_factory=list)
    total_tokens_used: int = 0
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_name: str = ""
    pending_attachments: list[FileAttachment] = field(default_factory=list)
    search_enabled: bool = False
    bookmarks: list[Bookmark] = field(default_factory=list)

    tokens_estimated: bool = False  # True when token count is client-side estimate
    gen_params: GenerationParams | None = None  # V3: active generation params

    # ── Phase 3: conversation branching ───────────────────────────────────
    active_branch: str = "main"
    # Branch name → message list (shares reference with `history` for "main")
    branches: dict[str, list[ChatMessage]] = field(default_factory=dict)
    # Branch name → bookmark list (shares reference with `bookmarks` for active)
    branch_bookmarks: dict[str, list[Bookmark]] = field(default_factory=dict)
    # Branch name → turn count in parent at divergence
    branch_diverges: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Bootstrap the ``main`` branch so it shares the history list."""
        if "main" not in self.branches:
            self.branches["main"] = self.history
            self.branch_bookmarks["main"] = self.bookmarks
            self.branch_diverges["main"] = 0


def _trim_history(history: list[ChatMessage], context_window: int) -> list[ChatMessage]:
    """Drop oldest non-system messages until the estimated size fits the context window.

    Uses 3.5 chars/token heuristic and reserves 80% of the window for the prompt
    so there is headroom for the model's response.
    """
    char_budget = int(context_window * 3.5 * 0.80)

    system_msgs = [m for m in history if m.role == "system"]
    non_system = [m for m in history if m.role != "system"]

    def _msg_chars(msg: ChatMessage) -> int:
        if isinstance(msg.content, str):
            return len(msg.content)
        return sum(len(p.text) for p in msg.content if isinstance(p, TextPart))

    available = char_budget - sum(_msg_chars(m) for m in system_msgs)

    while non_system and sum(_msg_chars(m) for m in non_system) > available:
        non_system.pop(0)

    return system_msgs + non_system


def _format_search_results(results: list[SearchResult], query: str) -> str:
    lines = [f"[Web Search: {query!r}]"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.title} — {r.url}")
        if r.snippet:
            lines.append(f"   {r.snippet}")
    return "\n".join(lines)


def _build_session(state: ChatState) -> Session:
    """Serialise a ``ChatState`` (including all branches) to a ``Session``."""
    branches: dict[str, BranchInfo] = {}
    for name, msgs in state.branches.items():
        if name == "main":
            continue  # main branch is stored in Session.messages
        branches[name] = BranchInfo(
            name=name,
            diverge_turn=state.branch_diverges.get(name, 0),
            messages=list(msgs),
            bookmarks=list(state.branch_bookmarks.get(name, [])),
        )
    return Session(
        id=state.session_id,
        provider=state.provider.name,
        model_id=state.model_id,
        messages=list(state.branches.get("main", state.history)),
        name=state.session_name,
        bookmarks=list(state.branch_bookmarks.get("main", state.bookmarks)),
        branches=branches,
    )


class ChatApp:
    """Interactive chat loop: banner → prompt → stream → repeat."""

    def __init__(
        self,
        ctx: AppContext,
        command_registry: CommandRegistry | None = None,
    ) -> None:
        self.ctx = ctx
        self._registry = command_registry or CommandRegistry.from_entry_points()

    async def run(self) -> int:
        """Run the interactive chat loop. Returns an exit code (0 = normal exit)."""
        ctx = self.ctx

        state = self._resolve_state()
        if state is None:
            return 1

        renderer = StreamRenderer(console=ctx.console, theme=ctx.theme)
        status_bar = ContextStatusBar(theme=ctx.theme, max_tokens=state.context_window)
        session = make_prompt_session(slash_commands=self._registry.names())

        print_banner(ctx.console, ctx.theme, __version__)
        ctx.console.print(
            Text(
                f"  Provider: {state.provider.name}  •  Model: {state.model_id}",
                style=ctx.theme.muted,
            )
        )
        ctx.console.print()

        while True:
            if state.total_tokens_used > 0:
                ctx.console.print(status_bar.render(state.total_tokens_used))

            try:
                user_input: str = await session.prompt_async([("class:prompt", "You: ")])
            except KeyboardInterrupt:
                ctx.console.print(Text("\nInterrupted.", style=ctx.theme.muted))
                break
            except EOFError:
                break

            stripped = user_input.strip()
            if not stripped:
                continue

            # Slash commands
            if stripped.startswith("/"):
                result = await self._registry.dispatch(stripped, ctx, state)
                if result.message:
                    style = ctx.theme.error if result.error else ctx.theme.secondary
                    ctx.console.print(Text(result.message, style=style))
                if result.should_exit:
                    break
                continue

            # Legacy bare "exit" / "quit" shortcuts
            if stripped.lower() in ("exit", "quit"):
                ctx.console.print(Text("Goodbye!", style=ctx.theme.primary))
                break

            # Accumulate extra content parts (search results + file attachments)
            extra_parts: list[ContentPart] = []

            if state.search_enabled:
                backend = ctx.search_registry.get_available(ctx.config.search_provider)
                if backend is not None:
                    try:
                        search_results = await backend.search(stripped)
                        if search_results:
                            extra_parts.append(
                                TextPart(_format_search_results(search_results, stripped))
                            )
                    except SearchError as exc:
                        ctx.console.print(
                            Text(f"  [Search failed: {exc.user_message}]", style=ctx.theme.error)
                        )

            for att in state.pending_attachments:
                if isinstance(att, TextAttachment):
                    extra_parts.append(TextPart(f"[File: {att.filename}]\n{att.content}"))
                elif isinstance(att, ImageAttachment):
                    extra_parts.append(att.image_part)
            state.pending_attachments.clear()

            if extra_parts:
                if stripped:
                    extra_parts.append(TextPart(stripped))
                user_msg = ChatMessage(role="user", content=extra_parts)
            else:
                user_msg = ChatMessage(role="user", content=stripped)
            state.history.append(user_msg)

            ctx.console.print(Text("\nAssistant: ", style=ctx.theme.accent))

            try:
                chunk_stream = state.provider.stream_chat(
                    messages=_trim_history(state.history, state.context_window),
                    model=state.model_id,
                    gen_params=state.gen_params,
                )
                full_text, usage = await renderer.stream(chunk_stream)
            except AnythinkError as exc:
                ctx.console.print(Text(f"\n[Error] {exc.user_message}", style=ctx.theme.error))
                state.history.pop()
                continue

            state.history.append(ChatMessage(role="assistant", content=full_text))
            if usage:
                state.total_tokens_used = usage.total_tokens
                if ctx.config.spend_tracking:
                    from anythink.spend.pricing import estimate_cost

                    cost = estimate_cost(state.provider.name, state.model_id, usage)
                    ctx.spend_tracker.record(
                        session_id=state.session_id,
                        model_id=state.model_id,
                        provider=state.provider.name,
                        usage=usage,
                        cost_usd=cost,
                    )
                    # Soft budget warning
                    limit = ctx.config.spend_budget_soft_limit
                    if limit is not None:
                        period = ctx.config.spend_budget_period
                        current_spend = (
                            ctx.spend_tracker.daily_total()
                            if period == "daily"
                            else ctx.spend_tracker.monthly_total()
                        )
                        ratio = current_spend / limit
                        if ratio >= 1.0:
                            ctx.console.print(
                                Text(
                                    f"  ⚠ Spend limit reached: "
                                    f"${current_spend:.4f} / ${limit:.2f} ({period})",
                                    style=ctx.theme.error,
                                )
                            )
                        elif ratio >= 0.8:
                            ctx.console.print(
                                Text(
                                    f"  ⚠ Approaching spend limit: "
                                    f"${current_spend:.4f} / ${limit:.2f} ({period})",
                                    style=ctx.theme.muted,
                                )
                            )

            ctx.console.print()

        # Autosave when configured and conversation is non-empty
        if ctx.config.session_autosave and state.history:
            chat_session = _build_session(state)
            ctx.session_manager.save(chat_session)

        return 0

    def _resolve_state(self) -> ChatState | None:
        """Resolve the active provider+model from config.

        Returns None and prints an error on failure.
        """
        ctx = self.ctx

        alias_name = ctx.config.default_model_alias
        if not alias_name:
            ctx.console.print(
                Text(
                    "No default model configured. Run `anythink setup` to get started.",
                    style=ctx.theme.error,
                )
            )
            return None

        alias: ModelAlias | None = ctx.model_registry.get(alias_name)
        if alias is None:
            ctx.console.print(
                Text(
                    f"Model alias '{alias_name}' not found. "
                    "Run `anythink model list` to see available aliases.",
                    style=ctx.theme.error,
                )
            )
            return None

        api_key = ctx.key_manager.get_key(alias.provider)

        try:
            provider = ctx.provider_registry.instantiate(
                alias.provider,
                api_key=api_key,
                base_url=ctx.config.local_servers.get(alias.provider),
            )
        except AnythinkError as exc:
            ctx.console.print(
                Text(
                    f"Failed to load provider '{alias.provider}': {exc.user_message}",
                    style=ctx.theme.error,
                )
            )
            return None

        if api_key is None and provider.requires_api_key:
            ctx.console.print(
                Text(
                    f"No API key for '{alias.provider}'. "
                    f"Run `anythink keys add {alias.provider}` to add one.",
                    style=ctx.theme.error,
                )
            )
            return None

        return ChatState(
            provider=provider,
            model_id=alias.model_id,
            context_window=alias.context_window,
            search_enabled=ctx.config.web_search_enabled,
            gen_params=alias.gen_params,
        )
