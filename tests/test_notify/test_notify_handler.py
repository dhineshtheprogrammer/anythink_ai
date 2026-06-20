"""Tests for the /voice and /notify slash command handlers."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

import pytest

from anythink.app.chat import ChatState
from anythink.app.context import AppContext
from anythink.commands.handlers import register_commands
from anythink.commands.registry import CommandRegistry
from anythink.config.manager import Paths
from anythink.notify.backends import NullBackend
from anythink.notify.notifier import Notifier


@pytest.fixture()
def registry() -> CommandRegistry:
    r = CommandRegistry()
    register_commands(r)
    return r


@pytest.fixture()
def ctx(xdg_dirs: Paths) -> AppContext:
    ctx = AppContext.create(paths=xdg_dirs, console_file=StringIO())
    # Replace notifier with test double
    ctx.notifier = Notifier(enabled=True, backend=NullBackend())
    return ctx


@pytest.fixture()
def state(ctx: AppContext) -> ChatState:
    provider = MagicMock()
    provider.name = "mock"
    return ChatState(provider=provider, model_id="gpt-4", context_window=8192)


# ── /voice ────────────────────────────────────────────────────────────────────


class TestVoiceCommand:
    async def test_voice_no_args_returns_request_action(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/voice", ctx, state)
        assert not result.error
        assert result.action == "voice_request"

    async def test_voice_model_valid(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/voice model tiny", ctx, state)
        assert not result.error
        assert "tiny" in (result.message or "")
        assert ctx.config.voice_model == "tiny"

    async def test_voice_model_invalid(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/voice model giant", ctx, state)
        assert result.error
        assert "giant" in (result.message or "")

    async def test_voice_model_all_valid_sizes(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        for model in ("tiny", "base", "small", "medium", "large", "turbo"):
            result = await registry.dispatch(f"/voice model {model}", ctx, state)
            assert not result.error, f"Model '{model}' should be valid"

    async def test_voice_language_set(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/voice language en", ctx, state)
        assert not result.error
        assert ctx.config.voice_language == "en"

    async def test_voice_language_clear(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/voice language", ctx, state)
        assert not result.error
        assert ctx.config.voice_language is None


# ── /notify ───────────────────────────────────────────────────────────────────


class TestNotifyCommand:
    async def test_notify_status(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/notify status", ctx, state)
        assert not result.error
        assert "Notifications" in (result.message or "")

    async def test_notify_status_no_args(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/notify", ctx, state)
        assert not result.error
        assert "Notifications" in (result.message or "")

    async def test_notify_on(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.notifier.set_enabled(False)
        result = await registry.dispatch("/notify on", ctx, state)
        assert not result.error
        assert ctx.notifier.enabled

    async def test_notify_off(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/notify off", ctx, state)
        assert not result.error
        assert not ctx.notifier.enabled

    async def test_notify_type_off(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/notify type rag_build_done off", ctx, state)
        assert not result.error
        assert not ctx.notifier.is_type_enabled("rag_build_done")

    async def test_notify_type_on(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        ctx.notifier.set_type_enabled("rag_build_done", False)
        result = await registry.dispatch("/notify type rag_build_done on", ctx, state)
        assert not result.error
        assert ctx.notifier.is_type_enabled("rag_build_done")

    async def test_notify_type_unknown(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/notify type banana on", ctx, state)
        assert result.error
        assert "banana" in (result.message or "")

    async def test_notify_type_invalid_flag(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/notify type rag_build_done maybe", ctx, state)
        assert result.error

    async def test_notify_type_missing_flag(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/notify type rag_build_done", ctx, state)
        assert result.error

    async def test_notify_unknown_subcommand(
        self, ctx: AppContext, state: ChatState, registry: CommandRegistry
    ) -> None:
        result = await registry.dispatch("/notify badcmd", ctx, state)
        assert result.error

    async def test_voice_registered(self, registry: CommandRegistry) -> None:
        assert registry.get("voice") is not None

    async def test_notify_registered(self, registry: CommandRegistry) -> None:
        assert registry.get("notify") is not None
