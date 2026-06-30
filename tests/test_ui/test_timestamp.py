"""Tests for ui/timestamp.py — format_timestamp pure function."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock


class TestFormatTimestampRelative:
    def test_just_now(self) -> None:
        from anythink.ui.timestamp import format_timestamp

        dt = datetime.now() - timedelta(seconds=30)
        assert format_timestamp(dt) == "just now"

    def test_minutes_ago(self) -> None:
        from anythink.ui.timestamp import format_timestamp

        dt = datetime.now() - timedelta(minutes=5)
        result = format_timestamp(dt)
        assert result == "5m ago"

    def test_hours_ago(self) -> None:
        from anythink.ui.timestamp import format_timestamp

        dt = datetime.now() - timedelta(hours=3)
        result = format_timestamp(dt)
        assert result == "3h ago"

    def test_yesterday(self) -> None:
        from anythink.ui.timestamp import format_timestamp

        dt = datetime.now() - timedelta(days=1)
        result = format_timestamp(dt)
        assert "Yesterday" in result
        assert ":" in result

    def test_same_year(self) -> None:
        from anythink.ui.timestamp import format_timestamp

        now = datetime.now()
        # 5 days ago, guaranteed same year unless it's Jan 1-5
        dt = now - timedelta(days=5)
        if dt.year == now.year:
            result = format_timestamp(dt)
            # Should have a short month name and time
            assert "," in result
            assert ":" in result

    def test_different_year(self) -> None:
        from anythink.ui.timestamp import format_timestamp

        dt = datetime(2020, 6, 15, 10, 30, 0)
        result = format_timestamp(dt)
        assert "2020" in result
        assert ":" in result

    def test_absolute_mode(self) -> None:
        from anythink.ui.timestamp import format_timestamp

        dt = datetime(2024, 3, 15, 14, 30, 45)
        mock_config = MagicMock()
        mock_config.timestamps = "absolute"
        result = format_timestamp(dt, config=mock_config)
        assert result == "14:30:45"

    def test_relative_mode_with_config(self) -> None:
        from anythink.ui.timestamp import format_timestamp

        mock_config = MagicMock()
        mock_config.timestamps = "relative"
        dt = datetime.now() - timedelta(seconds=10)
        result = format_timestamp(dt, config=mock_config)
        assert result == "just now"

    def test_no_config(self) -> None:
        from anythink.ui.timestamp import format_timestamp

        dt = datetime.now() - timedelta(seconds=5)
        result = format_timestamp(dt, config=None)
        assert result == "just now"
