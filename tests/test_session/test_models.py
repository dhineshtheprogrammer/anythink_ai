"""Tests for session/models.py."""

from __future__ import annotations

from datetime import datetime

from anythink.providers.base import ChatMessage, ImagePart, TextPart
from anythink.session.models import Session, _msg_from_dict, _msg_to_dict


class TestMsgToDict:
    def test_string_content_preserved(self) -> None:
        msg = ChatMessage(role="user", content="hello")
        d = _msg_to_dict(msg)
        assert d["content"] == "hello"
        assert d["role"] == "user"

    def test_timestamp_serialised(self) -> None:
        msg = ChatMessage(role="assistant", content="hi")
        d = _msg_to_dict(msg)
        assert "timestamp" in d
        datetime.fromisoformat(d["timestamp"])  # must parse without error

    def test_text_part_serialised(self) -> None:
        msg = ChatMessage(role="user", content=[TextPart("hello")])
        d = _msg_to_dict(msg)
        assert isinstance(d["content"], list)
        assert d["content"][0] == {"type": "text", "text": "hello"}

    def test_image_part_serialised(self) -> None:
        msg = ChatMessage(role="user", content=[ImagePart(b"\x89PNG", "image/png")])
        d = _msg_to_dict(msg)
        assert d["content"][0]["type"] == "image"
        assert d["content"][0]["mime_type"] == "image/png"
        assert isinstance(d["content"][0]["data"], str)  # base64 string

    def test_metadata_preserved(self) -> None:
        msg = ChatMessage(role="user", content="hi", metadata={"key": "val"})
        d = _msg_to_dict(msg)
        assert d["metadata"] == {"key": "val"}


class TestMsgFromDict:
    def test_string_content_round_trips(self) -> None:
        msg = ChatMessage(role="user", content="hello world")
        restored = _msg_from_dict(_msg_to_dict(msg))
        assert restored.content == "hello world"
        assert restored.role == "user"

    def test_text_part_round_trips(self) -> None:
        msg = ChatMessage(role="user", content=[TextPart("hi")])
        restored = _msg_from_dict(_msg_to_dict(msg))
        assert isinstance(restored.content, list)
        assert isinstance(restored.content[0], TextPart)
        assert restored.content[0].text == "hi"  # type: ignore[union-attr]

    def test_image_part_round_trips(self) -> None:
        raw_bytes = b"\x89PNG\r\n"
        msg = ChatMessage(role="user", content=[ImagePart(raw_bytes, "image/png")])
        restored = _msg_from_dict(_msg_to_dict(msg))
        assert isinstance(restored.content, list)
        img = restored.content[0]
        assert isinstance(img, ImagePart)
        assert img.data == raw_bytes
        assert img.mime_type == "image/png"

    def test_missing_timestamp_defaults_to_now(self) -> None:
        before = datetime.utcnow()
        restored = _msg_from_dict({"role": "user", "content": "hi"})
        after = datetime.utcnow()
        assert before <= restored.timestamp <= after

    def test_unknown_content_type_cast_to_string(self) -> None:
        # a dict that is neither str nor list
        restored = _msg_from_dict({"role": "user", "content": 42})
        assert restored.content == "42"


class TestSession:
    def test_new_generates_uuid(self) -> None:
        s1 = Session.new("groq", "llama3")
        s2 = Session.new("groq", "llama3")
        assert s1.id != s2.id
        assert len(s1.id) == 36  # UUID4 format

    def test_new_with_name(self) -> None:
        s = Session.new("openai", "gpt-4", name="my-chat")
        assert s.name == "my-chat"
        assert s.messages == []

    def test_to_dict_keys(self) -> None:
        s = Session.new("groq", "llama3", name="test")
        d = s.to_dict()
        for key in ("id", "provider", "model_id", "name", "created_at", "updated_at", "messages"):
            assert key in d

    def test_round_trip_empty_messages(self) -> None:
        s = Session.new("ollama", "llama2")
        restored = Session.from_dict(s.to_dict())
        assert restored.id == s.id
        assert restored.provider == "ollama"
        assert restored.model_id == "llama2"
        assert restored.messages == []

    def test_round_trip_with_messages(self) -> None:
        s = Session.new("groq", "llama3")
        s.messages.append(ChatMessage(role="user", content="hello"))
        s.messages.append(ChatMessage(role="assistant", content="hi there"))
        restored = Session.from_dict(s.to_dict())
        assert len(restored.messages) == 2
        assert restored.messages[0].content == "hello"
        assert restored.messages[1].role == "assistant"

    def test_from_dict_missing_timestamps_default(self) -> None:
        d = {"id": "abc", "provider": "p", "model_id": "m", "messages": []}
        s = Session.from_dict(d)
        assert isinstance(s.created_at, datetime)
        assert isinstance(s.updated_at, datetime)

    def test_from_dict_missing_optional_fields(self) -> None:
        d = {"id": "abc", "provider": "p", "model_id": "m"}
        s = Session.from_dict(d)
        assert s.name == ""
        assert s.messages == []
