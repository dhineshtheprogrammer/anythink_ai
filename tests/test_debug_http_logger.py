"""Tests for debug/http_logger.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.debug.http_logger import DebugHttpLogger, _mask_auth


class TestMaskAuth:
    def test_masks_authorization_header(self) -> None:
        headers = {"Authorization": "Bearer sk-realkey123", "Content-Type": "application/json"}
        result = _mask_auth(headers)
        assert result["Authorization"] == "Bearer sk-...***"
        assert result["Content-Type"] == "application/json"

    def test_case_insensitive_match(self) -> None:
        headers = {"authorization": "Bearer realkey"}
        result = _mask_auth(headers)
        assert result["authorization"] == "Bearer sk-...***"

    def test_passes_through_other_headers(self) -> None:
        headers = {"X-Custom": "value", "Accept": "application/json"}
        result = _mask_auth(headers)
        assert result == headers

    def test_empty_headers(self) -> None:
        assert _mask_auth({}) == {}


class TestDebugHttpLoggerInit:
    def test_init_no_path(self) -> None:
        logger = DebugHttpLogger()
        assert logger._log_path is None
        assert logger._logger is None
        assert logger._show_keys is False

    def test_init_with_path(self, tmp_path: Path) -> None:
        log_path = tmp_path / "debug.log"
        logger = DebugHttpLogger(log_path=log_path)
        assert logger._log_path == log_path

    def test_get_logger_no_path_returns_none(self) -> None:
        logger = DebugHttpLogger()
        assert logger._get_logger() is None

    def test_get_logger_creates_file_handler(self, tmp_path: Path) -> None:
        log_path = tmp_path / "logs" / "debug.log"
        logger = DebugHttpLogger(log_path=log_path)
        lg = logger._get_logger()
        assert lg is not None
        # Verify directory was created
        assert log_path.parent.exists()

    def test_get_logger_returns_cached(self, tmp_path: Path) -> None:
        log_path = tmp_path / "debug.log"
        logger = DebugHttpLogger(log_path=log_path)
        first = logger._get_logger()
        second = logger._get_logger()
        assert first is second

    def test_get_logger_os_error_returns_none(self, tmp_path: Path) -> None:
        log_path = tmp_path / "debug.log"
        logger = DebugHttpLogger(log_path=log_path)
        with patch(
            "anythink.debug.http_logger.RotatingFileHandler", side_effect=OSError("fail")
        ):
            result = logger._get_logger()
        assert result is None


class TestMakeHooks:
    def test_returns_request_and_response_hooks(self) -> None:
        logger = DebugHttpLogger()
        hooks = logger.make_hooks()
        assert "request" in hooks
        assert "response" in hooks
        assert len(hooks["request"]) == 1
        assert len(hooks["response"]) == 1

    async def test_on_request_no_logger_no_crash(self) -> None:
        logger = DebugHttpLogger()  # no path → no logger
        hooks = logger.make_hooks()
        on_request = hooks["request"][0]

        request = MagicMock()
        request.method = "POST"
        request.url = "https://api.anthropic.com/v1/messages"
        request.headers = {"Authorization": "Bearer key", "Content-Type": "application/json"}
        request.content = b'{"model": "claude-3"}'
        await on_request(request)  # should not raise

    async def test_on_request_with_logger_writes_line(self, tmp_path: Path) -> None:
        log_path = tmp_path / "debug.log"
        logger = DebugHttpLogger(log_path=log_path)
        hooks = logger.make_hooks()
        on_request = hooks["request"][0]

        request = MagicMock()
        request.method = "POST"
        request.url = "https://api.example.com/chat"
        request.headers = {"Authorization": "Bearer key", "Content-Type": "application/json"}
        request.content = b'{"model": "test"}'
        await on_request(request)
        assert log_path.exists()

    async def test_on_response_no_logger_no_crash(self) -> None:
        logger = DebugHttpLogger()  # no path → no logger
        hooks = logger.make_hooks()
        on_response = hooks["response"][0]

        response = MagicMock()
        response.request = MagicMock()
        response.status_code = 200
        response.headers = {"Content-Type": "application/json"}
        response.text = '{"result": "ok"}'
        response.aread = AsyncMock()
        await on_response(response)  # should not raise

    async def test_on_response_exception_silent(self) -> None:
        logger = DebugHttpLogger()
        hooks = logger.make_hooks()
        on_response = hooks["response"][0]

        # Passing a bad response that will raise inside the handler
        response = MagicMock()
        response.request = MagicMock()
        del response.status_code  # will cause AttributeError inside
        response.aread = AsyncMock()
        await on_response(response)  # should not raise — exception is swallowed

    async def test_on_request_masks_auth_by_default(self, tmp_path: Path) -> None:
        log_path = tmp_path / "debug.log"
        logger = DebugHttpLogger(log_path=log_path)
        # _show_keys is False by default
        hooks = logger.make_hooks()
        on_request = hooks["request"][0]

        request = MagicMock()
        request.method = "POST"
        request.url = "https://api.example.com/"
        request.headers = {"Authorization": "Bearer sk-realkey"}
        request.content = b""
        await on_request(request)

        content = log_path.read_text()
        assert "sk-realkey" not in content
        assert "sk-...***" in content
