"""OptimizeSettingsManager — YAML-backed persistence for /optimize panel state."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from anythink.optimize.models import OptimizeSettings


class OptimizeSettingsManager:
    """Persistent store for MMOS settings, backed by optimize_settings.yaml.

    Follows the ScheduleManager pattern: lazy-load on first access, dirty flag,
    save() is a no-op if nothing changed.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._settings: OptimizeSettings | None = None
        self._dirty = False

    def _load(self) -> OptimizeSettings:
        if self._settings is not None:
            return self._settings

        if not self._path.exists():
            self._settings = OptimizeSettings()
            return self._settings

        try:
            raw: dict[str, Any] = yaml.safe_load(self._path.read_text()) or {}
        except yaml.YAMLError:
            self._settings = OptimizeSettings()
            return self._settings

        self._settings = OptimizeSettings.from_dict(raw)
        return self._settings

    def get(self) -> OptimizeSettings:
        return self._load()

    def update(self, **kwargs: Any) -> OptimizeSettings:
        """Return updated settings after applying kwargs; persists immediately."""
        current = self._load()
        updated = replace(current, **kwargs)
        self._settings = updated
        self._dirty = True
        self.save()
        return updated

    def reset(self) -> OptimizeSettings:
        """Reset all settings to defaults and persist."""
        self._settings = OptimizeSettings()
        self._dirty = True
        self.save()
        return self._settings

    def save(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = self._load().to_dict()
        self._path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=True))
        self._dirty = False
