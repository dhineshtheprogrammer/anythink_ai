"""Tests for debug/http_logger.py — DebugHttpLogger and _mask_auth."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestMaskAuth:
    def test_masks_authorization_header(self) -> None:
        from anythink.debug.http_logger import _mask_auth

        result = _mask_auth({"Authorization": "Bearer sk-real-key-123", "Content-Type": "application/json"})
        assert result["Authorization"] == "Bearer sk-...***"
        assert result["Content-Type"] == "application/json"

    def test_case_insensitive_masking(self) -> None:
        from anythink.debug.http_logger import _mask_auth

        result = _mask_auth({"authorization": "Bearer secret"})
        assert result["authorization"] == "Bearer sk-...***"

    def test_no_auth_header_unchanged(self) -> None:
        from anythink.debug.http_logger import _mask_auth

        headers = {"Content-Type": "application/json", "Accept": "text/plain"}
        result = _mask_auth(headers)
        assert result == headers

    def test_empty_headers(self) -> None:
        from anythink.debug.http_logger import _mask_auth

        assert _mask_auth({}) == {}


class TestDebugHttpLoggerInit:
    def test_default_init(self) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        logger = DebugHttpLogger()
        assert logger._log_path is None
        assert logger._logger is None
        assert logger._show_keys is False
        assert logger._request_start_times == {}

    def test_init_with_path(self, tmp_path: Path) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        log_path = tmp_path / "logs" / "api.log"
        logger = DebugHttpLogger(log_path=log_path)
        assert logger._log_path == log_path


class TestGetLogger:
    def test_returns_none_when_no_path(self) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        logger = DebugHttpLogger()
        assert logger._get_logger() is None

    def test_creates_logger_with_path(self, tmp_path: Path) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        log_path = tmp_path / "api.log"
        logger = DebugHttpLogger(log_path=log_path)
        lg = logger._get_logger()
        assert lg is not None
        assert log_path.exists()

    def test_returns_cached_logger(self, tmp_path: Path) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        log_path = tmp_path / "api2.log"
        logger = DebugHttpLogger(log_path=log_path)
        lg1 = logger._get_logger()
        lg2 = logger._get_logger()
        assert lg1 is lg2

    def test_handles_oserror_gracefully(self, tmp_path: Path) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        log_path = tmp_path / "api.log"
        logger = DebugHttpLogger(log_path=log_path)
        with patch("anythink.debug.http_logger.RotatingFileHandler", side_effect=OSError("no permission")):
            result = logger._get_logger()
        assert result is None


class TestMakeHooks:
    def test_returns_dict_with_request_and_response(self) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        logger = DebugHttpLogger()
        hooks = logger.make_hooks()
        assert "request" in hooks
        assert "response" in hooks
        assert len(hooks["request"]) == 1
        assert len(hooks["response"]) == 1

    async def test_on_request_hook_runs_without_error(self, tmp_path: Path) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        log_path = tmp_path / "api.log"
        logger = DebugHttpLogger(log_path=log_path)
        hooks = logger.make_hooks()

        mock_request = MagicMock()
        mock_request.method = "POST"
        mock_request.url = "https://api.groq.com/v1/chat"
        mock_request.headers = {"Authorization": "Bearer sk-key", "Content-Type": "application/json"}
        mock_request.content = b'{"model": "llama3"}'

        on_request = hooks["request"][0]
        await on_request(mock_request)
        # Should have logged and created the log file
        assert log_path.exists()

    async def test_on_request_masks_auth_when_show_keys_false(self, tmp_path: Path) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        log_path = tmp_path / "api3.log"
        logger = DebugHttpLogger(log_path=log_path)
        logger._show_keys = False
        hooks = logger.make_hooks()

        mock_request = MagicMock()
        mock_request.method = "POST"
        mock_request.url = "https://api.openai.com"
        mock_request.headers = {"Authorization": "Bearer sk-real-secret"}
        mock_request.content = b"{}"

        await hooks["request"][0](mock_request)
        content = log_path.read_text()
        assert "sk-real-secret" not in content
        assert "sk-...***" in content

    async def test_on_response_hook_runs_without_error(self, tmp_path: Path) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        log_path = tmp_path / "api4.log"
        logger = DebugHttpLogger(log_path=log_path)
        hooks = logger.make_hooks()

        mock_response = MagicMock()
        mock_response.request = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.text = '{"id": "chatcmpl-123"}'
        mock_response.aread = AsyncMock()

        on_response = hooks["response"][0]
        await on_response(mock_response)

    async def test_on_request_hook_handles_exception_silently(self) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        logger = DebugHttpLogger()
        hooks = logger.make_hooks()

        broken_request = MagicMock()
        broken_request.headers = None  # will cause AttributeError in dict()

        # Should not raise — exceptions are suppressed
        await hooks["request"][0](broken_request)

    async def test_on_response_hook_handles_exception_silently(self) -> None:
        from anythink.debug.http_logger import DebugHttpLogger

        logger = DebugHttpLogger()
        hooks = logger.make_hooks()

        broken_response = MagicMock()
        broken_response.request = MagicMock()
        broken_response.aread = AsyncMock(side_effect=Exception("connection reset"))

        await hooks["response"][0](broken_response)
