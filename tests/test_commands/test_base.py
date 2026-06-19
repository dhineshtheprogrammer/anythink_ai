"""Tests for commands/base.py."""

from __future__ import annotations

from anythink.commands.base import CommandResult, SlashCommand


class TestCommandResult:
    def test_defaults(self) -> None:
        r = CommandResult()
        assert r.should_exit is False
        assert r.message is None
        assert r.error is False

    def test_exit_result(self) -> None:
        r = CommandResult(should_exit=True, message="Bye")
        assert r.should_exit is True
        assert r.message == "Bye"

    def test_error_result(self) -> None:
        r = CommandResult(error=True, message="oops")
        assert r.error is True


class TestSlashCommand:
    def test_fields(self) -> None:
        async def _h(ctx, args, state, registry):  # type: ignore[no-untyped-def]
            return CommandResult()

        cmd = SlashCommand(name="test", description="A test command", handler=_h)
        assert cmd.name == "test"
        assert cmd.description == "A test command"
        assert cmd.usage == ""

    def test_custom_usage(self) -> None:
        async def _h(ctx, args, state, registry):  # type: ignore[no-untyped-def]
            return CommandResult()

        cmd = SlashCommand(name="foo", description="d", handler=_h, usage="/foo <arg>")
        assert cmd.usage == "/foo <arg>"
