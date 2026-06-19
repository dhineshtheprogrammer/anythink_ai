"""Interactive multi-line input prompt using prompt_toolkit."""

from __future__ import annotations

from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings


def _build_bindings() -> KeyBindings:
    kb = KeyBindings()

    @kb.add("escape", "enter")  # Alt+Enter inserts a newline without submitting
    def _insert_newline(event: Any) -> None:
        event.current_buffer.insert_text("\n")

    return kb


def make_prompt_session(
    slash_commands: list[str] | None = None,
) -> PromptSession:  # type: ignore[type-arg]
    """Build a prompt_toolkit PromptSession with slash-command completion."""
    words = [f"/{cmd}" for cmd in (slash_commands or [])]
    return PromptSession(
        completer=WordCompleter(words, sentence=True),
        key_bindings=_build_bindings(),
    )
