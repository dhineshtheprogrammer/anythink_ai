"""Interactive chat loop orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.text import Text

from anythink import __version__
from anythink.app.context import AppContext
from anythink.commands.registry import CommandRegistry
from anythink.config.models import ModelAlias
from anythink.exceptions import AnythinkError
from anythink.providers.base import BaseProvider, ChatMessage, TokenUsage
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

            user_msg = ChatMessage(role="user", content=stripped)
            state.history.append(user_msg)

            ctx.console.print(Text("\nAssistant: ", style=ctx.theme.accent))

            try:
                chunk_stream = state.provider.stream_chat(
                    messages=state.history,
                    model=state.model_id,
                )
                full_text, usage = await renderer.stream(chunk_stream)
            except AnythinkError as exc:
                ctx.console.print(Text(f"\n[Error] {exc.user_message}", style=ctx.theme.error))
                state.history.pop()
                continue

            state.history.append(ChatMessage(role="assistant", content=full_text))
            if usage:
                state.total_tokens_used = usage.total_tokens

            ctx.console.print()

        return 0

    def _resolve_state(self) -> ChatState | None:
        """Resolve the active provider+model from config. Returns None and prints an error on failure."""
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
                    f"Model alias '{alias_name}' not found. Run `anythink model list` to see available aliases.",
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
                    f"No API key for '{alias.provider}'. Run `anythink keys add {alias.provider}` to add one.",
                    style=ctx.theme.error,
                )
            )
            return None

        return ChatState(
            provider=provider,
            model_id=alias.model_id,
            context_window=alias.context_window,
        )
