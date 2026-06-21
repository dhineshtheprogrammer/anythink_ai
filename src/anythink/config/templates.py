"""Prompt template library for Anythink."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from anythink.exceptions import ConfigError


@dataclass
class PromptTemplate:
    """A named prompt template with optional ``{{variable}}`` placeholders."""

    name: str
    body: str
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def variables(self) -> list[str]:
        """Return the list of placeholder names found in the body."""
        return re.findall(r"\{\{(\w+)\}\}", self.body)

    def render(self, variables: dict[str, str]) -> str:
        """Substitute ``{{key}}`` placeholders; raise ConfigError on any missing."""
        result = self.body
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", value)
        unresolved = re.findall(r"\{\{(\w+)\}\}", result)
        if unresolved:
            raise ConfigError(
                f"Template '{self.name}' has unresolved variables: {', '.join(unresolved)}",
                user_message=(
                    f"Missing template variables: {', '.join(unresolved)}. "
                    f"Provide them as key=value arguments."
                ),
            )
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "body": self.body,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptTemplate:
        created_at = (
            datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.utcnow()
        )
        return cls(
            name=data["name"],
            body=data["body"],
            description=data.get("description", ""),
            created_at=created_at,
        )


class TemplateManager:
    """Persistent store for prompt templates, backed by templates.yaml."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._templates: dict[str, PromptTemplate] | None = None
        self._dirty = False

    def _load(self) -> dict[str, PromptTemplate]:
        if self._templates is not None:
            return self._templates

        if not self._path.exists():
            self._templates = {}
            return self._templates

        try:
            raw: list[dict[str, Any]] = yaml.safe_load(self._path.read_text()) or []
        except yaml.YAMLError as e:
            raise ConfigError(f"Failed to parse templates.yaml: {e}") from e

        self._templates = {
            entry["name"]: PromptTemplate.from_dict(entry) for entry in raw if "name" in entry
        }
        return self._templates

    def save(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        templates = self._load()
        data = [t.to_dict() for t in sorted(templates.values(), key=lambda t: t.created_at)]
        self._path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        self._dirty = False

    def add(self, template: PromptTemplate) -> None:
        self._load()[template.name] = template
        self._dirty = True
        self.save()

    def remove(self, name: str) -> None:
        templates = self._load()
        if name not in templates:
            raise ConfigError(f"Template '{name}' not found.")
        del templates[name]
        self._dirty = True
        self.save()

    def get(self, name: str) -> PromptTemplate | None:
        return self._load().get(name)

    def list_all(self) -> list[PromptTemplate]:
        return sorted(self._load().values(), key=lambda t: t.created_at)

    def exists(self, name: str) -> bool:
        return name in self._load()
