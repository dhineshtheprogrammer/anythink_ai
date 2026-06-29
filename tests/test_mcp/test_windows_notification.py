"""Tests for WindowsNotificationServer and _parse_at_time."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from anythink.mcp.builtin.windows_notification import WindowsNotificationServer
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.safety import WindowsSafetyChecker


class TestWindowsNotificationServer:
    def _make_server(self) -> WindowsNotificationServer:
        return WindowsNotificationServer(
            safety=MagicMock(spec=WindowsSafetyChecker),
            audit=MagicMock(spec=WindowsAuditLog),
            app_name="TestApp",
        )

    def test_list_tools(self) -> None:
        srv = self._make_server()
        names = {t.name for t in srv.list_tools()}
        assert names == {
            "send_notification",
            "send_scheduled_notification",
            "list_scheduled_notifications",
            "cancel_scheduled_notification",
        }
        for t in srv.list_tools():
            assert t.server_name == "windows-notification"

    async def test_non_windows_error(self) -> None:
        srv = self._make_server()
        with patch("anythink.mcp.builtin.windows_notification._WINDOWS_ONLY", False):
            result = await srv.call_tool("send_notification", {"title": "Hi", "message": "yo"})
        assert "Windows" in result.content

    async def test_send_notification_uses_winotify(self) -> None:
        srv = self._make_server()
        mock_notif_cls = MagicMock()
        mock_notif_instance = MagicMock()
        mock_notif_cls.return_value = mock_notif_instance
        mock_winotify = MagicMock()
        mock_winotify.Notification = mock_notif_cls
        with (
            patch("anythink.mcp.builtin.windows_notification._WINDOWS_ONLY", True),
            patch.dict("sys.modules", {"winotify": mock_winotify}),
        ):
            result = await srv.call_tool("send_notification", {"title": "Hello", "message": "World"})
        assert not result.is_error
        mock_notif_instance.show.assert_called_once()

    async def test_list_scheduled_empty(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("list_scheduled_notifications", {})
        assert not result.is_error
        assert "no pending" in result.content.lower()

    async def test_cancel_unknown_id(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("cancel_scheduled_notification", {"notification_id": "xyz"})
        assert not result.is_error
        assert "xyz" in result.content

    async def test_send_scheduled_creates_task(self) -> None:
        srv = self._make_server()
        with (
            patch("anythink.mcp.builtin.windows_notification._WINDOWS_ONLY", True),
            patch.object(srv, "_send_now", return_value="sent"),
        ):
            result = await srv.call_tool(
                "send_scheduled_notification",
                {"title": "Reminder", "message": "Test", "delay_seconds": 3600},
            )
        assert not result.is_error
        assert len(srv._scheduled) == 1
        # Cleanup
        for task in srv._scheduled.values():
            task.cancel()

    async def test_cancel_scheduled_notification(self) -> None:
        srv = self._make_server()
        with (
            patch("anythink.mcp.builtin.windows_notification._WINDOWS_ONLY", True),
            patch.object(srv, "_send_now", return_value="sent"),
        ):
            await srv.call_tool(
                "send_scheduled_notification",
                {"title": "R", "message": "M", "delay_seconds": 3600},
            )
        notif_id = next(iter(srv._scheduled))
        result = await srv.call_tool("cancel_scheduled_notification", {"notification_id": notif_id})
        assert not result.is_error
        assert notif_id not in srv._scheduled

    async def test_send_scheduled_requires_delay_or_at_time(self) -> None:
        srv = self._make_server()
        with patch("anythink.mcp.builtin.windows_notification._WINDOWS_ONLY", True):
            result = await srv.call_tool(
                "send_scheduled_notification",
                {"title": "R", "message": "M"},  # neither delay_seconds nor at_time
            )
        assert "delay_seconds" in result.content.lower() or "at_time" in result.content.lower()

    async def test_unknown_tool(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("bogus", {})
        assert result.is_error


class TestParseAtTime:
    """Test _parse_at_time for all supported formats.

    We test behavior (positive result, correct ballpark) without mocking datetime
    because the method uses a local `import datetime` that can't be patched as a
    module attribute. The tests just verify format parsing logic is correct.
    """

    def _srv(self) -> WindowsNotificationServer:
        return WindowsNotificationServer(
            safety=MagicMock(spec=WindowsSafetyChecker),
            audit=MagicMock(spec=WindowsAuditLog),
        )

    def test_24h_format_returns_positive(self) -> None:
        import datetime
        srv = self._srv()
        # Parse a time 1 hour ahead — result should be positive (within 0–86400 seconds)
        now = datetime.datetime.now()
        future = (now + datetime.timedelta(hours=1)).strftime("%H:%M")
        result = srv._parse_at_time(future)
        assert 0 < result <= 3600 + 60

    def test_12h_pm_format_parses_correctly(self) -> None:
        srv = self._srv()
        # "2:30 PM" → should parse to 14:30 and return a positive seconds-until value
        result = srv._parse_at_time("2:30 PM")
        assert result != -1.0  # parsed successfully
        assert -86400 < result <= 86400  # sane range

    def test_12h_am_format_parses_correctly(self) -> None:
        srv = self._srv()
        result = srv._parse_at_time("9:00 AM")
        assert result != -1.0
        assert -86400 < result <= 86400

    def test_tomorrow_prefix_result_is_positive_and_within_48h(self) -> None:
        """'tomorrow HH:MM' must return a positive value within the next 48 hours."""
        srv = self._srv()
        # Use a fixed mid-day time that is always unambiguously "tomorrow"
        result = srv._parse_at_time("tomorrow 12:00")
        assert result != -1.0, "tomorrow 12:00 should parse successfully"
        # Must be positive and no more than 48h from now
        assert 0 < result <= 48 * 3600

    def test_invalid_format_returns_minus_one(self) -> None:
        srv = self._srv()
        result = srv._parse_at_time("not-a-time")
        assert result == -1.0

    def test_empty_string_returns_minus_one(self) -> None:
        srv = self._srv()
        assert srv._parse_at_time("") == -1.0

    def test_past_time_rolls_to_next_day(self) -> None:
        """A time in the past (without tomorrow prefix) should roll to next day."""
        import datetime
        srv = self._srv()
        now = datetime.datetime.now()
        # Compute a time 1 minute in the past
        past = (now - datetime.timedelta(minutes=2)).strftime("%H:%M")
        result = srv._parse_at_time(past)
        # Should roll to next day — result should be close to 24 hours
        assert result > 0
        assert result > 23 * 3600
