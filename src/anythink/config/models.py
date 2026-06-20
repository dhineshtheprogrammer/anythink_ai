"""Model alias registry for Anythink."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from anythink.exceptions import ConfigError


@dataclass
class ModelAlias:
    """A user-defined alias mapping a friendly name to a provider/model pair."""

    alias: str
    provider: str
    model_id: str
    context_window: int
    supports_vision: bool = False
    added_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "provider": self.provider,
            "model_id": self.model_id,
            "context_window": self.context_window,
            "supports_vision": self.supports_vision,
            "added_at": self.added_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelAlias:
        added_at = (
            datetime.fromisoformat(data["added_at"]) if "added_at" in data else datetime.utcnow()
        )
        return cls(
            alias=data["alias"],
            provider=data["provider"],
            model_id=data["model_id"],
            context_window=int(data.get("context_window", 4096)),
            supports_vision=bool(data.get("supports_vision", False)),
            added_at=added_at,
        )


class ModelRegistry:
    """Persistent store for model aliases, backed by models.yaml."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._aliases: dict[str, ModelAlias] | None = None  # lazy-loaded
        self._dirty = False

    def _load(self) -> dict[str, ModelAlias]:
        if self._aliases is not None:
            return self._aliases

        if not self._path.exists():
            self._aliases = {}
            return self._aliases

        try:
            raw: list[dict[str, Any]] = yaml.safe_load(self._path.read_text()) or []
        except yaml.YAMLError as e:
            raise ConfigError(f"Failed to parse models.yaml: {e}") from e

        self._aliases = {
            entry["alias"]: ModelAlias.from_dict(entry) for entry in raw if "alias" in entry
        }
        return self._aliases

    def save(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        aliases = self._load()
        data = [a.to_dict() for a in sorted(aliases.values(), key=lambda a: a.added_at)]
        self._path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        self._dirty = False

    def add(self, alias: ModelAlias) -> None:
        self._load()[alias.alias] = alias
        self._dirty = True
        self.save()

    def remove(self, alias: str) -> None:
        aliases = self._load()
        if alias not in aliases:
            raise ConfigError(f"Model alias '{alias}' not found.")
        del aliases[alias]
        self._dirty = True
        self.save()

    def get(self, alias: str) -> ModelAlias | None:
        return self._load().get(alias)

    def list_all(self) -> list[ModelAlias]:
        return sorted(self._load().values(), key=lambda a: a.added_at)

    def exists(self, alias: str) -> bool:
        return alias in self._load()
