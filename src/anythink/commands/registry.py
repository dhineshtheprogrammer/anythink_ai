"""CommandRegistry: registers and dispatches slash commands."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from anythink.commands.base import CommandResult, SlashCommand

if TYPE_CHECKING:
    from anythink.app.chat import ChatState
    from anythink.app.context import AppContext

_ENTRY_POINT_GROUP = "anythink.slash_commands"


class CommandRegistry:
    """Maps slash command names to handlers and dispatches invocations."""

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}

    def register(self, cmd: SlashCommand) -> None:
        """Add a command to the registry (overwrites any existing entry with the same name)."""
        self._commands[cmd.name.lower()] = cmd

    def get(self, name: str) -> SlashCommand | None:
        """Return the command for *name*, or None if not registered."""
        return self._commands.get(name.lower())

    def names(self) -> list[str]:
        """Return sorted list of all registered command names (without leading slash)."""
        return sorted(self._commands)

    async def dispatch(
        self,
        raw_input: str,
        ctx: AppContext,
        state: ChatState,
    ) -> CommandResult:
        """Parse */name [args]* and invoke the matching handler.

        Returns a result with ``error=True`` for unknown commands.
        """
        if not raw_input.startswith("/"):
            return CommandResult()

        parts = raw_input[1:].split(None, 1)
        name = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        cmd = self._commands.get(name)
        if cmd is None:
            return CommandResult(
                error=True,
                message=f"Unknown command '/{name}'. Type /help to see available commands.",
            )

        return await cmd.handler(ctx, args, state, self)

    @classmethod
    def from_entry_points(cls) -> CommandRegistry:
        """Build a registry from all ``anythink.slash_commands`` entry points."""
        registry = cls()
        for ep in entry_points(group=_ENTRY_POINT_GROUP):
            try:
                register_fn = ep.load()
                register_fn(registry)
            except Exception:
                pass  # skip broken plugins — don't crash startup
        return registry
