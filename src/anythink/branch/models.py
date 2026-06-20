"""Branch data model for conversation branching."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from anythink.bookmarks.models import Bookmark
from anythink.providers.base import ChatMessage


@dataclass
class BranchInfo:
    """A single conversation branch diverged from its parent at *diverge_turn*.

    ``diverge_turn`` is the number of messages that were in the parent branch
    at the moment this branch was created.  The branch's own ``messages`` list
    starts from that point forward.
    """

    name: str
    diverge_turn: int
    messages: list[ChatMessage] = field(default_factory=list)
    bookmarks: list[Bookmark] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        from anythink.session.models import _msg_to_dict  # avoid circular at module level

        return {
            "name": self.name,
            "diverge_turn": self.diverge_turn,
            "messages": [_msg_to_dict(m) for m in self.messages],
            "bookmarks": [b.to_dict() for b in self.bookmarks],
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BranchInfo:
        from anythink.session.models import _msg_from_dict

        ts = data.get("created_at")
        return cls(
            name=str(data["name"]),
            diverge_turn=int(data.get("diverge_turn", 0)),
            messages=[_msg_from_dict(m) for m in data.get("messages", [])],
            bookmarks=[Bookmark.from_dict(b) for b in data.get("bookmarks", [])],
            created_at=datetime.fromisoformat(ts) if ts else datetime.utcnow(),
        )
