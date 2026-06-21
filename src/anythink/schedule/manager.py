"""Schedule manager for Anythink — persists scheduled prompts to schedules.yaml."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from anythink.exceptions import ScheduleError
from anythink.schedule.models import ScheduledPrompt


class ScheduleManager:
    """Persistent store for scheduled prompts, backed by schedules.yaml."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._schedules: dict[str, ScheduledPrompt] | None = None
        self._dirty = False

    def _load(self) -> dict[str, ScheduledPrompt]:
        if self._schedules is not None:
            return self._schedules

        if not self._path.exists():
            self._schedules = {}
            return self._schedules

        try:
            raw: list[dict[str, Any]] = yaml.safe_load(self._path.read_text()) or []
        except yaml.YAMLError as e:
            raise ScheduleError(f"Failed to parse schedules.yaml: {e}") from e

        self._schedules = {
            entry["name"]: ScheduledPrompt.from_dict(entry) for entry in raw if "name" in entry
        }
        return self._schedules

    def save(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        schedules = self._load()
        data = [s.to_dict() for s in sorted(schedules.values(), key=lambda s: s.created_at)]
        self._path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        self._dirty = False

    def add(self, schedule: ScheduledPrompt) -> None:
        self._load()[schedule.name] = schedule
        self._dirty = True
        self.save()

    def remove(self, name: str) -> None:
        schedules = self._load()
        if name not in schedules:
            raise ScheduleError(f"Schedule '{name}' not found.")
        del schedules[name]
        self._dirty = True
        self.save()

    def get(self, name: str) -> ScheduledPrompt | None:
        return self._load().get(name)

    def list_all(self) -> list[ScheduledPrompt]:
        return sorted(self._load().values(), key=lambda s: s.created_at)

    def exists(self, name: str) -> bool:
        return name in self._load()

    def enable(self, name: str) -> None:
        schedules = self._load()
        if name not in schedules:
            raise ScheduleError(f"Schedule '{name}' not found.")
        from dataclasses import replace

        schedules[name] = replace(schedules[name], enabled=True)
        self._dirty = True
        self.save()

    def disable(self, name: str) -> None:
        schedules = self._load()
        if name not in schedules:
            raise ScheduleError(f"Schedule '{name}' not found.")
        from dataclasses import replace

        schedules[name] = replace(schedules[name], enabled=False)
        self._dirty = True
        self.save()

    def update_last_run(self, name: str, dt: datetime) -> None:
        schedules = self._load()
        if name not in schedules:
            raise ScheduleError(f"Schedule '{name}' not found.")
        from dataclasses import replace

        schedules[name] = replace(schedules[name], last_run=dt)
        self._dirty = True
        self.save()
