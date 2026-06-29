"""Tests for ScheduleManager."""

from __future__ import annotations

import pytest

from anythink.exceptions import ScheduleError
from anythink.schedule.manager import ScheduleManager
from anythink.schedule.models import ScheduledPrompt


class TestScheduleManager:
    def test_empty_list(self, xdg_dirs: Paths) -> None:
        mgr = ScheduleManager(xdg_dirs.schedules_file)
        assert mgr.list_all() == []

    def test_add_and_get(self, xdg_dirs: Paths) -> None:
        mgr = ScheduleManager(xdg_dirs.schedules_file)
        s = ScheduledPrompt("morning", "0 9 * * *", "Summarize emails")
        mgr.add(s)
        fetched = mgr.get("morning")
        assert fetched is not None
        assert fetched.cron_expr == "0 9 * * *"

    def test_exists(self, xdg_dirs: Paths) -> None:
        mgr = ScheduleManager(xdg_dirs.schedules_file)
        assert not mgr.exists("x")
        mgr.add(ScheduledPrompt("x", "* * * * *", "prompt"))
        assert mgr.exists("x")

    def test_remove(self, xdg_dirs: Paths) -> None:
        mgr = ScheduleManager(xdg_dirs.schedules_file)
        mgr.add(ScheduledPrompt("s1", "* * * * *", "p"))
        mgr.remove("s1")
        assert not mgr.exists("s1")

    def test_remove_missing_raises(self, xdg_dirs: Paths) -> None:
        mgr = ScheduleManager(xdg_dirs.schedules_file)
        with pytest.raises(ScheduleError):
            mgr.remove("nonexistent")

    def test_enable_disable(self, xdg_dirs: Paths) -> None:
        mgr = ScheduleManager(xdg_dirs.schedules_file)
        mgr.add(ScheduledPrompt("s", "* * * * *", "p"))
        mgr.disable("s")
        assert mgr.get("s").enabled is False  # type: ignore[union-attr]
        mgr.enable("s")
        assert mgr.get("s").enabled is True  # type: ignore[union-attr]

    def test_persistence_roundtrip(self, xdg_dirs: Paths) -> None:
        mgr1 = ScheduleManager(xdg_dirs.schedules_file)
        mgr1.add(ScheduledPrompt("daily", "0 8 * * *", "daily brief"))

        mgr2 = ScheduleManager(xdg_dirs.schedules_file)
        assert mgr2.exists("daily")
        assert mgr2.get("daily").cron_expr == "0 8 * * *"  # type: ignore[union-attr]

    def test_update_last_run(self, xdg_dirs: Paths) -> None:
        from datetime import datetime

        mgr = ScheduleManager(xdg_dirs.schedules_file)
        mgr.add(ScheduledPrompt("s", "* * * * *", "p"))
        now = datetime.utcnow()
        mgr.update_last_run("s", now)
        s = mgr.get("s")
        assert s is not None
        assert s.last_run is not None


class TestScheduledPrompt:
    def test_roundtrip(self) -> None:
        s = ScheduledPrompt(
            name="test",
            cron_expr="0 9 * * *",
            prompt="Do something",
            alias="myalias",
            output_file="/tmp/out.txt",
        )
        d = s.to_dict()
        restored = ScheduledPrompt.from_dict(d)
        assert restored.name == s.name
        assert restored.cron_expr == s.cron_expr
        assert restored.alias == s.alias
        assert restored.output_file == s.output_file

    def test_defaults(self) -> None:
        s = ScheduledPrompt("s", "* * * * *", "p")
        assert s.enabled is True
        assert s.last_run is None
        assert s.alias is None


class TestScheduleManagerEdgeCases:
    def test_save_when_not_dirty_is_noop(self, xdg_dirs) -> None:
        mgr = ScheduleManager(xdg_dirs.schedules_file)
        mgr.save()  # should not raise — early return when not dirty

    def test_load_yaml_error_raises(self, xdg_dirs) -> None:
        xdg_dirs.schedules_file.write_text(": invalid: yaml: {")
        mgr = ScheduleManager(xdg_dirs.schedules_file)
        with pytest.raises(Exception):
            mgr.list_all()

    def test_enable_missing_raises(self, xdg_dirs) -> None:
        mgr = ScheduleManager(xdg_dirs.schedules_file)
        with pytest.raises(ScheduleError):
            mgr.enable("nonexistent")

    def test_disable_missing_raises(self, xdg_dirs) -> None:
        mgr = ScheduleManager(xdg_dirs.schedules_file)
        with pytest.raises(ScheduleError):
            mgr.disable("nonexistent")

    def test_update_last_run_missing_raises(self, xdg_dirs) -> None:
        from datetime import datetime

        mgr = ScheduleManager(xdg_dirs.schedules_file)
        with pytest.raises(ScheduleError):
            mgr.update_last_run("nonexistent", datetime.utcnow())


class TestScheduledPromptWithLastRun:
    def test_roundtrip_with_last_run(self) -> None:
        from datetime import datetime

        now = datetime.utcnow()
        s = ScheduledPrompt("s", "* * * * *", "p")
        s = ScheduledPrompt(
            name="s",
            cron_expr="* * * * *",
            prompt="p",
            last_run=now,
        )
        d = s.to_dict()
        restored = ScheduledPrompt.from_dict(d)
        assert restored.last_run is not None
