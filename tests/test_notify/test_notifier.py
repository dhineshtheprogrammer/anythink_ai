"""Tests for notify/notifier.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from anythink.notify.backends import NullBackend
from anythink.notify.notifier import (
    NOTIFICATION_DEFAULTS,
    SLOW_EXEC_S,
    SLOW_RESPONSE_S,
    Notifier,
)


def _notifier(enabled: bool = True, **toggles: bool) -> Notifier:
    """Create a Notifier with a NullBackend for tests."""
    return Notifier(config_toggles=toggles, enabled=enabled, backend=NullBackend())


class TestNotifierDefaults:
    def test_all_types_enabled_by_default(self) -> None:
        n = _notifier()
        # Only types that explicitly default to True should be enabled by default.
        # Some V4 types (e.g. rate_limit_switch) intentionally default to False.
        for t, default_on in NOTIFICATION_DEFAULTS.items():
            assert n.is_type_enabled(t) is default_on

    def test_enabled_globally(self) -> None:
        n = _notifier()
        assert n.enabled

    def test_backend_name(self) -> None:
        n = _notifier()
        assert n.backend_name == "NullBackend"

    def test_thresholds_are_positive(self) -> None:
        assert SLOW_RESPONSE_S > 0
        assert SLOW_EXEC_S > 0

    def test_notification_defaults_not_empty(self) -> None:
        assert len(NOTIFICATION_DEFAULTS) >= 5


class TestNotifierGlobalToggle:
    def test_set_enabled_false_disables_all(self) -> None:
        n = _notifier()
        n.set_enabled(False)
        assert not n.enabled
        for t in NOTIFICATION_DEFAULTS:
            assert not n.is_type_enabled(t)

    def test_set_enabled_true_re_enables(self) -> None:
        n = _notifier(enabled=False)
        n.set_enabled(True)
        assert n.enabled
        assert n.is_type_enabled("rag_build_done")


class TestNotifierPerTypeToggle:
    def test_disable_single_type(self) -> None:
        n = _notifier()
        n.set_type_enabled("rag_build_done", False)
        assert not n.is_type_enabled("rag_build_done")
        assert n.is_type_enabled("slow_response")  # others unchanged

    def test_enable_previously_disabled_type(self) -> None:
        n = _notifier(rag_build_done=False)
        assert not n.is_type_enabled("rag_build_done")
        n.set_type_enabled("rag_build_done", True)
        assert n.is_type_enabled("rag_build_done")

    def test_unknown_type_defaults_to_true(self) -> None:
        n = _notifier()
        assert n.is_type_enabled("nonexistent_type")

    def test_config_toggles_override_defaults(self) -> None:
        n = _notifier(exec_done=False)
        assert not n.is_type_enabled("exec_done")


class TestNotifierNotify:
    def test_notify_calls_backend_when_enabled(self) -> None:
        mock_backend = MagicMock()
        n = Notifier(enabled=True, backend=mock_backend)
        n.notify("rag_build_done", "Title", "Message")
        mock_backend.send.assert_called_once_with("Title", "Message")

    def test_notify_skips_when_globally_disabled(self) -> None:
        mock_backend = MagicMock()
        n = Notifier(enabled=False, backend=mock_backend)
        n.notify("rag_build_done", "Title", "Message")
        mock_backend.send.assert_not_called()

    def test_notify_skips_when_type_disabled(self) -> None:
        mock_backend = MagicMock()
        n = Notifier(config_toggles={"rag_build_done": False}, enabled=True, backend=mock_backend)
        n.notify("rag_build_done", "Title", "Message")
        mock_backend.send.assert_not_called()

    def test_notify_swallows_backend_exceptions(self) -> None:
        mock_backend = MagicMock()
        mock_backend.send.side_effect = Exception("platform error")
        n = Notifier(enabled=True, backend=mock_backend)
        n.notify("slow_response", "t", "m")  # must not raise

    def test_notify_all_default_types(self) -> None:
        mock_backend = MagicMock()
        n = Notifier(enabled=True, backend=mock_backend)
        for t in NOTIFICATION_DEFAULTS:
            n.notify(t, f"Title for {t}", "msg")
        # Only types that default to True will trigger backend.send
        expected_calls = sum(1 for v in NOTIFICATION_DEFAULTS.values() if v)
        assert mock_backend.send.call_count == expected_calls


class TestNotifierStatus:
    def test_status_returns_dict(self) -> None:
        n = _notifier()
        snap = n.status()
        assert isinstance(snap, dict)
        assert "enabled" in snap
        assert "backend" in snap

    def test_status_reflects_toggles(self) -> None:
        n = _notifier(exec_done=False)
        snap = n.status()
        assert snap["type:exec_done"] is False
        assert snap["type:rag_build_done"] is True

    def test_status_after_disable(self) -> None:
        n = _notifier()
        n.set_enabled(False)
        assert not n.status()["enabled"]
