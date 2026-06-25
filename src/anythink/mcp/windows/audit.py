"""Persistent JSONL audit log for all Windows MCP tool calls."""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WindowsAuditLog:
    """Rolling JSONL audit log — one record per tool call, 10 MB rotation, 5 backups."""

    def __init__(self, log_path: str) -> None:
        self._log_path = Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        self._logger = logging.getLogger(f"anythink.windows_audit.{id(self)}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        self._handler = logging.handlers.RotatingFileHandler(
            str(self._log_path),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(self._handler)

    def log(
        self,
        session_id: str,
        server: str,
        tool: str,
        tier: int,
        arguments: dict[str, Any],
        confirmation_status: str,
        outcome: str,
        duration_s: float,
        error: str | None = None,
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "server": server,
            "tool": tool,
            "tier": tier,
            "arguments": arguments,
            "confirmation_status": confirmation_status,
            "outcome": outcome,
            "duration_s": round(duration_s, 4),
            "error": error,
        }
        self._logger.debug(json.dumps(record, default=str))

    def get_recent(
        self,
        n: int = 20,
        tool_filter: str | None = None,
        date_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._log_path.exists():
            return []

        today = datetime.now(timezone.utc).date().isoformat()
        results: list[dict[str, Any]] = []

        try:
            lines = self._log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if tool_filter and record.get("tool") != tool_filter:
                continue
            if date_filter == "today" and not record.get("timestamp", "").startswith(today):
                continue

            results.append(record)
            if len(results) >= n:
                break

        return results

    def export_to_text(self, output_path: str) -> None:
        records = self.get_recent(n=10_000)
        lines = [
            f"{'Timestamp':<30} {'Server':<22} {'Tool':<32} {'Tier':<6} {'Outcome':<22} {'Duration':>8}",
            "-" * 120,
        ]
        for r in records:
            lines.append(
                f"{r.get('timestamp',''):<30} "
                f"{r.get('server',''):<22} "
                f"{r.get('tool',''):<32} "
                f"{r.get('tier','')!s:<6} "
                f"{r.get('outcome',''):<22} "
                f"{r.get('duration_s',0):>8.3f}s"
            )
        Path(output_path).write_text("\n".join(lines), encoding="utf-8")

    def clear(self) -> None:
        self._handler.close()
        self._logger.removeHandler(self._handler)
        try:
            self._log_path.write_text("", encoding="utf-8")
        except OSError:
            pass
        self._handler = logging.handlers.RotatingFileHandler(
            str(self._log_path),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(self._handler)

    @property
    def log_path(self) -> str:
        return str(self._log_path)
