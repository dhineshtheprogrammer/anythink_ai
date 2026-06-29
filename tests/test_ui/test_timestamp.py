"""Tests for ui/timestamp.py."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from anythink.ui.timestamp import format_timestamp


def _config(mode: str = "relative") -> MagicMock:
    cfg = MagicMock()
    cfg.timestamps = mode
    return cfg


class TestFormatTimestamp:
    def test_absolute_mode_returns_hhmmss(self) -> None:
        dt = datetime(2025, 6, 1, 14, 30, 45)
        result = format_timestamp(dt, _config("absolute"))
        assert result == "14:30:45"

    def test_no_config_defaults_to_relative(self) -> None:
        dt = datetime.now() - timedelta(seconds=10)
        result = format_timestamp(dt, None)
        assert result == "just now"

    def test_just_now_under_60_seconds(self) -> None:
        dt = datetime.now() - timedelta(seconds=30)
        result = format_timestamp(dt, _config())
        assert result == "just now"

    def test_minutes_ago(self) -> None:
        dt = datetime.now() - timedelta(minutes=5)
        result = format_timestamp(dt, _config())
        assert "m ago" in result

    def test_hours_ago(self) -> None:
        dt = datetime.now() - timedelta(hours=3)
        result = format_timestamp(dt, _config())
        assert "h ago" in result

    def test_yesterday(self) -> None:
        from datetime import date

        import pytest

        today = date.today()
        yesterday_date = today - timedelta(days=1)
        # Must be > 86400 seconds ago (past the "hours ago" guard) but still days_diff=1.
        # Use yesterday at 00:01 to maximize the seconds gap.
        dt = datetime.combine(yesterday_date, datetime.min.time()).replace(hour=0, minute=1)
        now = datetime.now()
        seconds = (now - dt).total_seconds()
        days_diff = (now.date() - dt.date()).days
        if seconds < 86400 or days_diff != 1:
            pytest.skip("Skipping yesterday test near midnight boundary")
        result = format_timestamp(dt, _config())
        assert "Yesterday" in result

    def test_same_year_shows_month_day(self) -> None:
        dt = datetime.now() - timedelta(days=10)
        result = format_timestamp(dt, _config())
        # Should not include the year since it's the same year
        assert str(datetime.now().year) not in result

    def test_older_includes_year(self) -> None:
        dt = datetime(2020, 3, 15, 10, 30)
        result = format_timestamp(dt, _config())
        assert "2020" in result

    def test_config_relative_mode_same_as_no_config(self) -> None:
        dt = datetime.now() - timedelta(seconds=30)
        assert format_timestamp(dt, _config("relative")) == format_timestamp(dt, None)
