"""Bookmark dataclass for flagged AI responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Bookmark:
    """A user-flagged assistant message within a session.

    ``turn_index`` is the position of the assistant ``ChatMessage`` in
    ``Session.messages``; it is stable across saves/loads because the
    message list is append-only within a session.
    """

    turn_index: int
    label: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "label": self.label,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Bookmark:
        ts = data.get("created_at")
        return cls(
            turn_index=int(data["turn_index"]),
            label=str(data.get("label", "")),
            created_at=datetime.fromisoformat(ts) if ts else datetime.utcnow(),
        )
