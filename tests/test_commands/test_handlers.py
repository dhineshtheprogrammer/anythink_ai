"""Tests for commands/handlers.py."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

import pytest

from anythink.app.chat import ChatState
from anythink.app.context import AppContext
from anythink.commands.handlers import register_commands
from anythink.commands.registry import CommandRegistry
from anythink.config.manager import Paths
from anythink.config.personas import Persona, PersonaManager
from anythink.providers.base import ChatMessage, TokenUsage


@pytest.fixture()
def registry() -> CommandRegistry:
    r = CommandRegistry()
    register_commands(r)
    return r


@pytest.fixture()
def ctx(xdg_dirs: Paths) -> AppContext:
    return AppContext.create(paths=xdg_dirs, console_file=StringIO())


@pytest.fixture()
def state(ctx: AppContext) -> ChatState:
    provider = MagicMock()
    provider.name = "mock"
    return ChatState(provider=provider, model_id="llama3", context_window=8192)


class TestRegisterCommands:
    def test_all_builtin_commands_registered(self, registry: CommandRegistry) -> None:
        expected = {"help", "clear", "history", "tokens", "model", "persona", "exit", "quit"}
        assert expected.issubset(set(registry.names()))


class TestHelpCommand:
    async def test_help_lists_commands(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/help", ctx, state)
        assert result.message is not None
        assert "help" in result.message
        assert "exit" in result.message

    async def test_help_not_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/help", ctx, state)
        assert result.error is False


class TestClearCommand:
    async def test_clear_removes_user_and_assistant_messages(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [
            ChatMessage(role="user", content="hello"),
            ChatMessage(role="assistant", content="hi"),
        ]
        result = await registry.dispatch("/clear", ctx, state)
        assert state.history == []
        assert "cleared" in (result.message or "").lower()

    async def test_clear_preserves_system_messages(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [
            ChatMessage(role="system", content="You are a pirate."),
            ChatMessage(role="user", content="hello"),
        ]
        await registry.dispatch("/clear", ctx, state)
        assert len(state.history) == 1
        assert state.history[0].role == "system"

    async def test_clear_resets_token_count(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.total_tokens_used = 5000
        await registry.dispatch("/clear", ctx, state)
        assert state.total_tokens_used == 0


class TestHistoryCommand:
    async def test_history_empty(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/history", ctx, state)
        assert "No messages" in (result.message or "")

    async def test_history_shows_messages(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [
            ChatMessage(role="user", content="What is 2+2?"),
            ChatMessage(role="assistant", content="4"),
        ]
        result = await registry.dispatch("/history", ctx, state)
        assert "[user]" in (result.message or "")
        assert "What is 2+2?" in (result.message or "")

    async def test_history_truncates_long_content(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="x" * 200)]
        result = await registry.dispatch("/history", ctx, state)
        assert "…" in (result.message or "")

    async def test_history_shows_limit_note_over_10(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [
            ChatMessage(role="user", content=f"msg {i}") for i in range(15)
        ]
        result = await registry.dispatch("/history", ctx, state)
        assert "showing last 10" in (result.message or "")

    async def test_history_multimodal_shows_label(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        from anythink.providers.base import TextPart
        state.history = [ChatMessage(role="user", content=[TextPart("hi")])]
        result = await registry.dispatch("/history", ctx, state)
        assert "[multimodal" in (result.message or "")


class TestTokensCommand:
    async def test_tokens_shows_counts(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.total_tokens_used = 1234
        result = await registry.dispatch("/tokens", ctx, state)
        assert "1,234" in (result.message or "")
        assert "8,192" in (result.message or "")

    async def test_tokens_shows_percentage(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.total_tokens_used = 4096
        result = await registry.dispatch("/tokens", ctx, state)
        assert "50.0%" in (result.message or "")

    async def test_tokens_zero_context_no_crash(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.context_window = 0
        state.total_tokens_used = 0
        result = await registry.dispatch("/tokens", ctx, state)
        assert result.message is not None


class TestModelCommand:
    async def test_model_shows_provider_and_model(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/model", ctx, state)
        assert "mock" in (result.message or "")
        assert "llama3" in (result.message or "")


class TestPersonaCommand:
    async def test_persona_no_args_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/persona", ctx, state)
        assert result.error is True
        assert "Usage" in (result.message or "")

    async def test_persona_clear_removes_system_messages(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [
            ChatMessage(role="system", content="You are a pirate."),
            ChatMessage(role="user", content="hi"),
        ]
        result = await registry.dispatch("/persona clear", ctx, state)
        assert all(m.role != "system" for m in state.history)
        assert "cleared" in (result.message or "").lower()

    async def test_persona_set_unknown_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/persona nonexistent", ctx, state)
        assert result.error is True
        assert "not found" in (result.message or "")

    async def test_persona_set_known_prepends_system_message(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.persona_manager.add(Persona(name="pirate", system_prompt="Speak like a pirate."))
        result = await registry.dispatch("/persona pirate", ctx, state)
        assert result.error is False
        assert state.history[0].role == "system"
        assert "pirate" in state.history[0].content  # type: ignore[operator]

    async def test_persona_replaces_existing_system_message(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        ctx.persona_manager.add(Persona(name="chef", system_prompt="You are a chef."))
        ctx.persona_manager.add(Persona(name="pirate", system_prompt="Speak pirate."))
        state.history = [ChatMessage(role="system", content="old persona")]
        await registry.dispatch("/persona pirate", ctx, state)
        system_msgs = [m for m in state.history if m.role == "system"]
        assert len(system_msgs) == 1
        assert "pirate" in system_msgs[0].content.lower()  # type: ignore[operator]


class TestSessionCommand:
    async def test_session_no_args_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session", ctx, state)
        assert result.error is True
        assert "Usage" in (result.message or "")

    async def test_session_unknown_sub_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session bloop", ctx, state)
        assert result.error is True

    async def test_session_list_empty(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session list", ctx, state)
        assert "No saved sessions" in (result.message or "")

    async def test_session_save_no_name(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="hi")]
        result = await registry.dispatch("/session save", ctx, state)
        assert result.error is False
        assert len(ctx.session_manager.list_sessions()) == 1

    async def test_session_save_with_name(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="hi")]
        await registry.dispatch("/session save my-chat", ctx, state)
        sessions = ctx.session_manager.list_sessions()
        assert sessions[0].name == "my-chat"

    async def test_session_list_shows_saved_sessions(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="hi")]
        await registry.dispatch("/session save chat1", ctx, state)
        result = await registry.dispatch("/session list", ctx, state)
        assert "chat1" in (result.message or "")

    async def test_session_load_unknown_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session load nobody", ctx, state)
        assert result.error is True

    async def test_session_load_no_arg_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session load", ctx, state)
        assert result.error is True

    async def test_session_load_restores_history(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="loaded msg")]
        await registry.dispatch("/session save myload", ctx, state)
        state.history = []
        result = await registry.dispatch("/session load myload", ctx, state)
        assert result.error is False
        assert len(state.history) == 1
        assert state.history[0].content == "loaded msg"

    async def test_session_delete_unknown_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session delete nobody", ctx, state)
        assert result.error is True

    async def test_session_delete_no_arg_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session delete", ctx, state)
        assert result.error is True

    async def test_session_delete_removes_session(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="bye")]
        await registry.dispatch("/session save todele", ctx, state)
        await registry.dispatch("/session delete todele", ctx, state)
        assert ctx.session_manager.list_sessions() == []

    async def test_session_rename_no_args_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session rename", ctx, state)
        assert result.error is True

    async def test_session_rename_one_arg_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session rename oldname", ctx, state)
        assert result.error is True

    async def test_session_rename_unknown_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/session rename nobody newname", ctx, state)
        assert result.error is True

    async def test_session_rename_updates_name(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        state.history = [ChatMessage(role="user", content="hello")]
        await registry.dispatch("/session save oldname", ctx, state)
        await registry.dispatch("/session rename oldname newname", ctx, state)
        sessions = ctx.session_manager.list_sessions()
        assert sessions[0].name == "newname"


class TestExitCommand:
    async def test_exit_sets_should_exit(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/exit", ctx, state)
        assert result.should_exit is True

    async def test_quit_sets_should_exit(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/quit", ctx, state)
        assert result.should_exit is True

    async def test_exit_has_goodbye_message(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/exit", ctx, state)
        assert result.message is not None
