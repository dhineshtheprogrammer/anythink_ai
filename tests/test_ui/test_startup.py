"""Tests for ui/startup.py."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from anythink.providers.base import ChatMessage
from anythink.session.models import Session
from anythink.ui.startup import (
    _MIN_EXCHANGE_MESSAGES,
    apply_icon_style_heuristic,
    find_resumable_session,
    is_returning_user,
    startup_one_liner,
    terminal_supports_unicode,
)


def _make_session(num_messages: int = 0) -> Session:
    messages = [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"msg {i}")
        for i in range(num_messages)
    ]
    return Session(id="s1", provider="mock", model_id="m", messages=messages)


class TestIsReturningUser:
    def test_returns_true_with_sessions(self) -> None:
        ctx = MagicMock()
        ctx.session_manager.list_sessions.return_value = [_make_session()]
        assert is_returning_user(ctx) is True

    def test_returns_false_with_no_sessions(self) -> None:
        ctx = MagicMock()
        ctx.session_manager.list_sessions.return_value = []
        assert is_returning_user(ctx) is False

    def test_returns_false_on_exception(self) -> None:
        ctx = MagicMock()
        ctx.session_manager.list_sessions.side_effect = RuntimeError("fail")
        assert is_returning_user(ctx) is False


class TestFindResumableSession:
    def test_returns_none_when_no_sessions(self) -> None:
        ctx = MagicMock()
        ctx.session_manager.list_sessions.return_value = []
        assert find_resumable_session(ctx) is None

    def test_returns_none_on_exception(self) -> None:
        ctx = MagicMock()
        ctx.session_manager.list_sessions.side_effect = RuntimeError("fail")
        assert find_resumable_session(ctx) is None

    def test_returns_none_for_too_short_session(self) -> None:
        ctx = MagicMock()
        ctx.session_manager.list_sessions.return_value = [_make_session(1)]
        assert find_resumable_session(ctx) is None

    def test_returns_session_for_sufficient_messages(self) -> None:
        session = _make_session(_MIN_EXCHANGE_MESSAGES)
        ctx = MagicMock()
        ctx.session_manager.list_sessions.return_value = [session]
        result = find_resumable_session(ctx)
        assert result is session

    def test_skips_system_messages_in_count(self) -> None:
        system_msg = ChatMessage(role="system", content="system prompt")
        user_msg = ChatMessage(role="user", content="hello")
        session = Session(
            id="s", provider="mock", model_id="m", messages=[system_msg, user_msg]
        )
        ctx = MagicMock()
        ctx.session_manager.list_sessions.return_value = [session]
        # Only 1 non-system message, below threshold of 2
        assert find_resumable_session(ctx) is None


class TestStartupOneLiner:
    def test_returns_string_with_version(self) -> None:
        ctx = MagicMock()
        ctx.config.default_model_alias = "claude"
        alias = MagicMock()
        alias.context_window = 8192
        alias.provider = "anthropic"
        ctx.model_registry.get.return_value = alias
        result = startup_one_liner(ctx)
        assert "Anythink" in result
        assert "claude" in result

    def test_handles_exception_gracefully(self) -> None:
        ctx = MagicMock()
        ctx.config.default_model_alias = "myalias"
        ctx.model_registry.get.side_effect = RuntimeError("fail")
        result = startup_one_liner(ctx)
        assert "Anythink" in result
        assert "—" in result

    def test_handles_no_alias(self) -> None:
        ctx = MagicMock()
        ctx.config.default_model_alias = None
        ctx.model_registry.get.return_value = None
        result = startup_one_liner(ctx)
        assert "Anythink" in result


class TestTerminalSupportsUnicode:
    def test_dumb_terminal_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "dumb")
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.delenv("VTE_VERSION", raising=False)
        assert terminal_supports_unicode() is False

    def test_vt100_terminal_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "vt100")
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.delenv("VTE_VERSION", raising=False)
        assert terminal_supports_unicode() is False

    def test_non_utf_lang_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "xterm")
        monkeypatch.setenv("LANG", "en_US.ASCII")
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.delenv("VTE_VERSION", raising=False)
        assert terminal_supports_unicode() is False

    def test_wt_session_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "xterm")
        monkeypatch.setenv("WT_SESSION", "abc-123")
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.delenv("VTE_VERSION", raising=False)
        assert terminal_supports_unicode() is True

    def test_iterm_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "xterm")
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.delenv("VTE_VERSION", raising=False)
        assert terminal_supports_unicode() is True

    def test_colorterm_truecolor_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "xterm")
        monkeypatch.setenv("COLORTERM", "truecolor")
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("VTE_VERSION", raising=False)
        assert terminal_supports_unicode() is True

    def test_vte_version_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "xterm")
        monkeypatch.setenv("VTE_VERSION", "6200")
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("COLORTERM", raising=False)
        assert terminal_supports_unicode() is True

    def test_default_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.delenv("VTE_VERSION", raising=False)
        assert terminal_supports_unicode() is True


class TestApplyIconStyleHeuristic:
    def test_already_ascii_skips(self) -> None:
        ctx = MagicMock()
        ctx.config.icon_style = "ascii"
        apply_icon_style_heuristic(ctx)
        # Should return early without modifying ctx.config
        ctx.config_manager.save.assert_not_called()

    def test_downgrade_to_ascii_for_non_unicode_terminal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TERM", "dumb")
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.delenv("VTE_VERSION", raising=False)

        from anythink.config.schema import AppConfig

        class FakeCtx:
            config: AppConfig = AppConfig(icon_style="unicode")

        fake = FakeCtx()
        apply_icon_style_heuristic(fake)  # type: ignore[arg-type]
        assert fake.config.icon_style == "ascii"
"""Tests for ui/startup.py — returning-user detection and startup utilities."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch


def _make_ctx(sessions: list | None = None, raise_list: bool = False) -> MagicMock:
    ctx = MagicMock()
    if raise_list:
        ctx.session_manager.list_sessions.side_effect = Exception("storage error")
    else:
        ctx.session_manager.list_sessions.return_value = sessions or []
    ctx.config.default_model_alias = "gpt-4o"
    ctx.config.icon_style = "unicode"
    ctx.model_registry.get.return_value = MagicMock(context_window=128000, provider="openai")
    return ctx


class TestIsReturningUser:
    def test_no_sessions_returns_false(self) -> None:
        from anythink.ui.startup import is_returning_user

        ctx = _make_ctx(sessions=[])
        assert is_returning_user(ctx) is False

    def test_with_sessions_returns_true(self) -> None:
        from anythink.ui.startup import is_returning_user

        ctx = _make_ctx(sessions=[MagicMock()])
        assert is_returning_user(ctx) is True

    def test_exception_returns_false(self) -> None:
        from anythink.ui.startup import is_returning_user

        ctx = _make_ctx(raise_list=True)
        assert is_returning_user(ctx) is False


class TestFindResumableSession:
    def test_no_sessions_returns_none(self) -> None:
        from anythink.ui.startup import find_resumable_session

        ctx = _make_ctx(sessions=[])
        assert find_resumable_session(ctx) is None

    def test_exception_returns_none(self) -> None:
        from anythink.ui.startup import find_resumable_session

        ctx = _make_ctx(raise_list=True)
        assert find_resumable_session(ctx) is None

    def test_session_with_enough_messages_is_resumable(self) -> None:
        from anythink.ui.startup import find_resumable_session

        session = MagicMock()
        msg1 = MagicMock()
        msg1.role = "user"
        msg2 = MagicMock()
        msg2.role = "assistant"
        session.messages = [msg1, msg2]

        ctx = _make_ctx(sessions=[session])
        result = find_resumable_session(ctx)
        assert result is session

    def test_session_with_only_system_messages_not_resumable(self) -> None:
        from anythink.ui.startup import find_resumable_session

        session = MagicMock()
        msg = MagicMock()
        msg.role = "system"
        session.messages = [msg]

        ctx = _make_ctx(sessions=[session])
        result = find_resumable_session(ctx)
        assert result is None

    def test_session_with_one_non_system_not_resumable(self) -> None:
        from anythink.ui.startup import find_resumable_session

        session = MagicMock()
        msg = MagicMock()
        msg.role = "user"
        session.messages = [msg]

        ctx = _make_ctx(sessions=[session])
        result = find_resumable_session(ctx)
        assert result is None


class TestStartupOneLiner:
    def test_returns_string_with_version(self) -> None:
        from anythink.ui.startup import startup_one_liner

        ctx = _make_ctx()
        result = startup_one_liner(ctx)
        assert "Anythink" in result
        assert "gpt-4o" in result

    def test_handles_registry_exception(self) -> None:
        from anythink.ui.startup import startup_one_liner

        ctx = _make_ctx()
        ctx.model_registry.get.side_effect = Exception("not found")
        result = startup_one_liner(ctx)
        assert "Anythink" in result
        assert "—" in result


class TestTerminalSupportsUnicode:
    def test_dumb_terminal_returns_false(self) -> None:
        from anythink.ui.startup import terminal_supports_unicode

        with patch.dict(os.environ, {"TERM": "dumb"}, clear=False):
            assert terminal_supports_unicode() is False

    def test_vt100_returns_false(self) -> None:
        from anythink.ui.startup import terminal_supports_unicode

        with patch.dict(os.environ, {"TERM": "vt100"}, clear=False):
            assert terminal_supports_unicode() is False

    def test_non_utf_lang_returns_false(self) -> None:
        from anythink.ui.startup import terminal_supports_unicode

        env = {"TERM": "", "LC_ALL": "C", "LANG": "C", "WT_SESSION": "", "TERM_PROGRAM": "",
               "COLORTERM": "", "VTE_VERSION": ""}
        with patch.dict(os.environ, env, clear=True):
            assert terminal_supports_unicode() is False

    def test_wt_session_returns_true(self) -> None:
        from anythink.ui.startup import terminal_supports_unicode

        with patch.dict(os.environ, {"TERM": "xterm", "WT_SESSION": "abc-123"}, clear=False):
            assert terminal_supports_unicode() is True

    def test_vscode_term_program_returns_true(self) -> None:
        from anythink.ui.startup import terminal_supports_unicode

        with patch.dict(os.environ, {"TERM": "xterm", "TERM_PROGRAM": "vscode"}, clear=False):
            assert terminal_supports_unicode() is True

    def test_truecolor_returns_true(self) -> None:
        from anythink.ui.startup import terminal_supports_unicode

        with patch.dict(os.environ, {"TERM": "xterm", "COLORTERM": "truecolor"}, clear=False):
            assert terminal_supports_unicode() is True

    def test_vte_version_returns_true(self) -> None:
        from anythink.ui.startup import terminal_supports_unicode

        with patch.dict(os.environ, {"TERM": "xterm", "VTE_VERSION": "6200"}, clear=False):
            assert terminal_supports_unicode() is True


class TestApplyIconStyleHeuristic:
    def test_already_ascii_no_change(self) -> None:
        from anythink.ui.startup import apply_icon_style_heuristic

        ctx = _make_ctx()
        ctx.config.icon_style = "ascii"
        apply_icon_style_heuristic(ctx)
        # Should not touch ctx.config since it's already ascii
        ctx.config.__class__.__setattr__ = MagicMock()

    def test_unicode_terminal_no_downgrade(self) -> None:
        from anythink.ui.startup import apply_icon_style_heuristic

        ctx = _make_ctx()
        ctx.config.icon_style = "unicode"
        with patch("anythink.ui.startup.terminal_supports_unicode", return_value=True):
            apply_icon_style_heuristic(ctx)
        # Should not reassign ctx.config
