"""Core types for the slash command system."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anythink.app.chat import ChatState
    from anythink.app.context import AppContext
    from anythink.commands.registry import CommandRegistry


@dataclass
class CommandResult:
    """Return value from a slash command handler."""

    should_exit: bool = False  # True → break out of the chat loop
    message: str | None = None  # optional text to print after handling
    error: bool = False  # True → print message in error style
    action: str = ""  # optional TUI-layer signal, e.g. "undo_request"
    extra: dict[str, Any] = field(default_factory=dict)  # tool-run params for TUI workers


CommandHandler = Callable[
    ["AppContext", str, "ChatState", "CommandRegistry"],
    Awaitable[CommandResult],
]


@dataclass
class SlashCommand:
    """A registered slash command."""

    name: str  # e.g. "help"  (no leading slash)
    description: str
    handler: CommandHandler
    usage: str = field(default="")  # e.g. "/help [command]"
