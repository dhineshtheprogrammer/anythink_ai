"""Data model for scheduled prompts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ScheduledPrompt:
    """A named prompt that runs automatically on a cron schedule."""

    name: str
    cron_expr: str  # 5-field cron expression, e.g. "0 9 * * 1"
    prompt: str
    alias: str | None = None  # model alias; None = use default
    output_file: str | None = None  # write result here; None = notification only
    enabled: bool = True
    last_run: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "cron_expr": self.cron_expr,
            "prompt": self.prompt,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
        }
        if self.alias is not None:
            d["alias"] = self.alias
        if self.output_file is not None:
            d["output_file"] = self.output_file
        if self.last_run is not None:
            d["last_run"] = self.last_run.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduledPrompt:
        created_at = (
            datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.utcnow()
        )
        last_run: datetime | None = None
        if "last_run" in data and data["last_run"]:
            last_run = datetime.fromisoformat(data["last_run"])
        return cls(
            name=data["name"],
            cron_expr=data["cron_expr"],
            prompt=data["prompt"],
            alias=data.get("alias"),
            output_file=data.get("output_file"),
            enabled=bool(data.get("enabled", True)),
            last_run=last_run,
            created_at=created_at,
        )
