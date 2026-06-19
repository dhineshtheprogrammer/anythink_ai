"""Session dataclass with YAML serialisation."""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from anythink.providers.base import ChatMessage, ImagePart, TextPart


def _msg_to_dict(msg: ChatMessage) -> dict[str, Any]:
    if isinstance(msg.content, str):
        content: Any = msg.content
    else:
        parts: list[dict[str, Any]] = []
        for part in msg.content:
            if isinstance(part, TextPart):
                parts.append({"type": "text", "text": part.text})
            elif isinstance(part, ImagePart):
                parts.append({
                    "type": "image",
                    "data": base64.b64encode(part.data).decode(),
                    "mime_type": part.mime_type,
                })
        content = parts
    return {
        "role": msg.role,
        "content": content,
        "timestamp": msg.timestamp.isoformat(),
        "metadata": msg.metadata,
    }


def _msg_from_dict(data: dict[str, Any]) -> ChatMessage:
    raw = data["content"]
    if isinstance(raw, str):
        content: str | list[TextPart | ImagePart] = raw
    elif isinstance(raw, list):
        reconstructed: list[TextPart | ImagePart] = []
        for item in raw:
            if item.get("type") == "text":
                reconstructed.append(TextPart(item["text"]))
            elif item.get("type") == "image":
                reconstructed.append(
                    ImagePart(
                        data=base64.b64decode(item["data"]),
                        mime_type=item["mime_type"],
                    )
                )
        content = reconstructed
    else:
        content = str(raw)

    ts_str = data.get("timestamp")
    timestamp = datetime.fromisoformat(ts_str) if ts_str else datetime.utcnow()
    return ChatMessage(
        role=data["role"],
        content=content,
        timestamp=timestamp,
        metadata=data.get("metadata", {}),
    )


@dataclass
class Session:
    """A persisted conversation with its full message history."""

    id: str
    provider: str
    model_id: str
    messages: list[ChatMessage]
    name: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def new(cls, provider: str, model_id: str, name: str = "") -> Session:
        """Create a fresh session with a new UUID."""
        return cls(
            id=str(uuid.uuid4()),
            provider=provider,
            model_id=model_id,
            messages=[],
            name=name,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "model_id": self.model_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [_msg_to_dict(m) for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        def _parse_dt(key: str) -> datetime:
            val = data.get(key)
            return datetime.fromisoformat(val) if val else datetime.utcnow()

        return cls(
            id=data["id"],
            provider=data.get("provider", ""),
            model_id=data.get("model_id", ""),
            name=data.get("name", ""),
            created_at=_parse_dt("created_at"),
            updated_at=_parse_dt("updated_at"),
            messages=[_msg_from_dict(m) for m in data.get("messages", [])],
        )
