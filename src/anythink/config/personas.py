"""Persona management for Anythink."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from anythink.exceptions import ConfigError


@dataclass
class Persona:
    """A named system prompt that shapes AI behavior for a session."""

    name: str
    system_prompt: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Persona:
        created_at = (
            datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.utcnow()
        )
        return cls(
            name=data["name"],
            system_prompt=data["system_prompt"],
            created_at=created_at,
        )


class PersonaManager:
    """Persistent store for personas, backed by personas.yaml."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._personas: dict[str, Persona] | None = None
        self._dirty = False

    def _load(self) -> dict[str, Persona]:
        if self._personas is not None:
            return self._personas

        if not self._path.exists():
            self._personas = {}
            return self._personas

        try:
            raw: list[dict[str, Any]] = yaml.safe_load(self._path.read_text()) or []
        except yaml.YAMLError as e:
            raise ConfigError(f"Failed to parse personas.yaml: {e}") from e

        self._personas = {
            entry["name"]: Persona.from_dict(entry) for entry in raw if "name" in entry
        }
        return self._personas

    def save(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        personas = self._load()
        data = [p.to_dict() for p in sorted(personas.values(), key=lambda p: p.created_at)]
        self._path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        self._dirty = False

    def add(self, persona: Persona) -> None:
        self._load()[persona.name] = persona
        self._dirty = True
        self.save()

    def remove(self, name: str) -> None:
        personas = self._load()
        if name not in personas:
            raise ConfigError(f"Persona '{name}' not found.")
        del personas[name]
        self._dirty = True
        self.save()

    def get(self, name: str) -> Persona | None:
        return self._load().get(name)

    def list_all(self) -> list[Persona]:
        return sorted(self._load().values(), key=lambda p: p.created_at)

    def exists(self, name: str) -> bool:
        return name in self._load()
