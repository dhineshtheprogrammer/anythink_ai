"""Tests for the Anythink exception hierarchy (V1 + V2 additions)."""

from __future__ import annotations

import pytest

from anythink.exceptions import (
    AnythinkError,
    BranchError,
    BrowseError,
    MCPError,
    NotificationError,
    RAGError,
    ToolExecutionError,
    VoiceError,
)

V2_EXCEPTIONS = [
    RAGError,
    ToolExecutionError,
    BrowseError,
    MCPError,
    VoiceError,
    BranchError,
    NotificationError,
]


@pytest.mark.parametrize("exc_cls", V2_EXCEPTIONS)
def test_v2_exceptions_subclass_base(exc_cls: type[AnythinkError]) -> None:
    assert issubclass(exc_cls, AnythinkError)


@pytest.mark.parametrize("exc_cls", V2_EXCEPTIONS)
def test_user_message_defaults_to_message(exc_cls: type[AnythinkError]) -> None:
    err = exc_cls("internal detail")
    assert str(err) == "internal detail"
    assert err.user_message == "internal detail"


@pytest.mark.parametrize("exc_cls", V2_EXCEPTIONS)
def test_user_message_override(exc_cls: type[AnythinkError]) -> None:
    err = exc_cls("internal detail", user_message="friendly")
    assert err.user_message == "friendly"
