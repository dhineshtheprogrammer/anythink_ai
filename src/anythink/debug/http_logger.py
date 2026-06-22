"""HTTP-level API request/response logger for /debug api."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


def _mask_auth(headers: dict[str, str]) -> dict[str, str]:
    """Replace Authorization header value with a masked placeholder."""
    out: dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() == "authorization":
            out[k] = "Bearer sk-...***"
        else:
            out[k] = v
    return out


class DebugHttpLogger:
    """Captures raw HTTP API traffic via httpx event hooks."""

    MAX_BYTES = 50 * 1024 * 1024  # 50 MB rolling log

    def __init__(self, log_path: Path | None = None) -> None:
        self._log_path = log_path
        self._logger: logging.Logger | None = None
        self._show_keys: bool = False
        self._request_start_times: dict[int, float] = {}

    def _get_logger(self) -> logging.Logger | None:
        if self._log_path is None:
            return None
        if self._logger is not None:
            return self._logger
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            logger = logging.getLogger(f"anythink.api_debug.{id(self)}")
            logger.setLevel(logging.DEBUG)
            logger.propagate = False
            handler = RotatingFileHandler(
                self._log_path,
                maxBytes=self.MAX_BYTES,
                backupCount=2,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            self._logger = logger
        except OSError:
            pass
        return self._logger

    def make_hooks(self) -> dict[str, list[Callable[..., Any]]]:
        """Return an httpx event_hooks dict."""
        logger = self

        async def _on_request(request: Any) -> None:
            try:
                req_id = id(request)
                logger._request_start_times[req_id] = time.monotonic()
                headers = dict(request.headers)
                if not logger._show_keys:
                    headers = _mask_auth(headers)
                body = request.content.decode("utf-8", errors="replace")[:2000]
                line = (
                    f"\n── REQUEST {request.method} {request.url} ──\n"
                    f"Headers: {headers}\n"
                    f"Body: {body}\n"
                )
                lg = logger._get_logger()
                if lg:
                    lg.debug(line)
            except Exception:  # nosec B110
                pass

        async def _on_response(response: Any) -> None:
            try:
                req_id = id(response.request)
                t_start = logger._request_start_times.pop(req_id, None)
                round_trip_ms = (time.monotonic() - t_start) * 1000 if t_start else 0.0
                await response.aread()
                body = response.text[:2000]
                line = (
                    f"\n── RESPONSE {response.status_code} "
                    f"({round_trip_ms:.0f}ms) ──\n"
                    f"Headers: {dict(response.headers)}\n"
                    f"Body: {body}\n"
                )
                lg = logger._get_logger()
                if lg:
                    lg.debug(line)
            except Exception:  # nosec B110
                pass

        return {"request": [_on_request], "response": [_on_response]}
