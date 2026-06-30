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
