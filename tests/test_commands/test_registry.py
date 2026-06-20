"""Tests for commands/registry.py."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from anythink.app.chat import ChatState
from anythink.app.context import AppContext
from anythink.commands.base import CommandResult, SlashCommand
from anythink.commands.registry import CommandRegistry
from anythink.config.manager import Paths


async def _noop(ctx, args, state, registry):  # type: ignore[no-untyped-def]
    return CommandResult(message="noop called")


async def _exit(ctx, args, state, registry):  # type: ignore[no-untyped-def]
    return CommandResult(should_exit=True, message="bye")


@pytest.fixture()
def registry() -> CommandRegistry:
    r = CommandRegistry()
    r.register(SlashCommand("help", "Show help", _noop))
    r.register(SlashCommand("exit", "Exit", _exit))
    return r


@pytest.fixture()
def ctx(xdg_dirs: Paths) -> AppContext:
    return AppContext.create(paths=xdg_dirs, console_file=StringIO())


@pytest.fixture()
def state(ctx: AppContext) -> ChatState:
    from unittest.mock import MagicMock

    provider = MagicMock()
    provider.name = "mock"
    return ChatState(provider=provider, model_id="test-model", context_window=4096)


class TestRegister:
    def test_register_and_get(self, registry: CommandRegistry) -> None:
        cmd = registry.get("help")
        assert cmd is not None
        assert cmd.name == "help"

    def test_get_unknown_returns_none(self, registry: CommandRegistry) -> None:
        assert registry.get("nope") is None

    def test_names_sorted(self, registry: CommandRegistry) -> None:
        assert registry.names() == ["exit", "help"]

    def test_register_overwrites(self, registry: CommandRegistry) -> None:
        async def _new(ctx, args, state, reg):  # type: ignore[no-untyped-def]
            return CommandResult(message="new")

        registry.register(SlashCommand("help", "new desc", _new))
        assert registry.get("help").description == "new desc"  # type: ignore[union-attr]

    def test_name_normalised_to_lowercase(self, registry: CommandRegistry) -> None:
        async def _h(ctx, args, state, reg):  # type: ignore[no-untyped-def]
            return CommandResult()

        registry.register(SlashCommand("UPPER", "u", _h))
        assert registry.get("upper") is not None
        assert registry.get("UPPER") is not None


class TestDispatch:
    async def test_known_command_invoked(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/help", ctx, state)
        assert result.message == "noop called"

    async def test_unknown_command_returns_error(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/bogus", ctx, state)
        assert result.error is True
        assert "bogus" in (result.message or "")

    async def test_non_slash_input_returns_empty_result(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("hello", ctx, state)
        assert result.should_exit is False
        assert result.message is None

    async def test_exit_command_sets_should_exit(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/exit", ctx, state)
        assert result.should_exit is True

    async def test_args_stripped_and_passed(self, ctx: AppContext, state: ChatState) -> None:
        received: list[str] = []

        async def _capture(c, args, s, reg):  # type: ignore[no-untyped-def]
            received.append(args)
            return CommandResult()

        r = CommandRegistry()
        r.register(SlashCommand("test", "t", _capture))
        await r.dispatch("/test  hello world  ", ctx, state)
        assert received == ["hello world"]

    async def test_command_name_case_insensitive(
        self, registry: CommandRegistry, ctx: AppContext, state: ChatState
    ) -> None:
        result = await registry.dispatch("/HELP", ctx, state)
        assert result.message == "noop called"


class TestFromEntryPoints:
    def test_loads_builtin_commands(self) -> None:
        registry = CommandRegistry.from_entry_points()
        assert "help" in registry.names()
        assert "exit" in registry.names()
        assert "clear" in registry.names()

    def test_bad_entry_point_skipped(self) -> None:
        bad_ep = MagicMock()
        bad_ep.load.side_effect = ImportError("broken plugin")
        with patch("anythink.commands.registry.entry_points", return_value=[bad_ep]):
            registry = CommandRegistry.from_entry_points()
        assert registry.names() == []

    def test_failing_register_fn_skipped(self) -> None:
        def _bad_register(reg: CommandRegistry) -> None:
            raise RuntimeError("oops")

        bad_ep = MagicMock()
        bad_ep.load.return_value = _bad_register
        with patch("anythink.commands.registry.entry_points", return_value=[bad_ep]):
            registry = CommandRegistry.from_entry_points()
        assert registry.names() == []
