"""DebugManager — central coordinator for V3.2.0 debug infrastructure."""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anythink.debug.models import RequestDebugRecord
    from anythink.providers.base import GenerationParams


class DebugManager:
    """Central coordinator for all debug state and captured request records.

    Always instantiated (zero cost when inactive); debug mode must be
    explicitly enabled via enable() or toggle(). All instrumentation in
    _stream_response() is guarded by is_active() so there is no overhead
    when debug is off.
    """

    MAX_RECORDS = 100

    def __init__(self) -> None:
        self._records: deque[RequestDebugRecord] = deque(maxlen=self.MAX_RECORDS)
        self._active: bool = False
        self._level: int = 2
        self._api_logging: bool = False
        self._panel_open: bool = False
        self._request_counter: int = 0
        self._pending_record: RequestDebugRecord | None = None
        self._export_active: bool = False
        self._export_path: Path | None = None
        self._http_client: Any = None  # httpx.AsyncClient | None, lazy

    # ── state accessors ───────────────────────────────────────────────────

    def is_active(self) -> bool:
        return self._active

    def level(self) -> int:
        return self._level

    def api_logging_active(self) -> bool:
        return self._api_logging

    def panel_open(self) -> bool:
        return self._panel_open

    # ── state mutators ────────────────────────────────────────────────────

    def enable(self, level: int = 2) -> None:
        self._active = True
        self._level = max(1, min(3, level))

    def disable(self) -> None:
        self._active = False

    def toggle(self) -> bool:
        """Toggle debug mode; return the new active state."""
        if self._active:
            self.disable()
        else:
            self.enable(self._level)
        return self._active

    def set_level(self, n: int) -> None:
        self._level = max(1, min(3, n))

    def toggle_api_logging(self) -> bool:
        """Toggle HTTP-level API logging; return the new state."""
        self._api_logging = not self._api_logging
        if not self._api_logging:
            self._http_client = None
        return self._api_logging

    def toggle_panel(self) -> bool:
        """Toggle the debug side panel; return the new state."""
        self._panel_open = not self._panel_open
        return self._panel_open

    # ── request lifecycle ─────────────────────────────────────────────────

    def begin_request(
        self,
        session_id: str,
        model_id: str,
        provider_name: str,
        alias_name: str,
        prompt_payload: list[dict[str, Any]],
        gen_params: GenerationParams | None,
        t_start: float,
    ) -> RequestDebugRecord:
        """Allocate a new RequestDebugRecord for the current in-flight request."""
        from anythink.debug.models import RequestDebugRecord

        self._request_counter += 1
        record = RequestDebugRecord(
            request_id=self._request_counter,
            session_id=session_id,
            timestamp=datetime.utcnow(),
            model_id=model_id,
            provider_name=provider_name,
            alias_name=alias_name,
            prompt_payload=prompt_payload,
            gen_params=gen_params,
            t_start=t_start,
        )
        self._pending_record = record
        return record

    def finalize_request(self, record: RequestDebugRecord) -> None:
        """Commit the completed record to the session deque."""
        self._pending_record = None
        self._records.append(record)
        if self._export_active and self._export_path is not None:
            self._append_export(record)

    # ── record access ─────────────────────────────────────────────────────

    def latest(self) -> RequestDebugRecord | None:
        """Return the most recently finalised record, or None."""
        return self._records[-1] if self._records else None

    def get(self, request_id: int) -> RequestDebugRecord | None:
        """Return the record for the given request_id, or None."""
        for rec in self._records:
            if rec.request_id == request_id:
                return rec
        return None

    def all_records(self) -> list[RequestDebugRecord]:
        return list(self._records)

    # ── export ────────────────────────────────────────────────────────────

    def export_json(self, path: Path) -> Path:
        """Export all captured records to a structured JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [self._record_to_dict(r) for r in self._records]
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def export_txt(self, path: Path) -> Path:
        """Export all captured records to a human-readable text file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        for rec in self._records:
            lines.append(f"=== Request #{rec.request_id}  {rec.timestamp.isoformat()} ===")
            lines.append(f"Model: {rec.alias_name}  Provider: {rec.provider_name}")
            if rec.total_wall_ms():
                lines.append(f"Total: {rec.total_wall_ms():.0f}ms")
            if rec.ttft_ms() is not None:
                lines.append(f"TTFT: {rec.ttft_ms():.0f}ms")
            if rec.tokens_per_second:
                lines.append(f"TPS: {rec.tokens_per_second:.1f} tok/s")
            if rec.stop_reason:
                lines.append(f"Stop reason: {rec.stop_reason}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _append_export(self, record: RequestDebugRecord) -> None:
        """Append one record to the live export file."""
        if self._export_path is None:
            return
        try:
            entry = self._record_to_dict(record)
            with self._export_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            pass

    def _record_to_dict(self, rec: RequestDebugRecord) -> dict[str, Any]:
        return {
            "request_id": rec.request_id,
            "session_id": rec.session_id,
            "timestamp": rec.timestamp.isoformat(),
            "model_id": rec.model_id,
            "provider_name": rec.provider_name,
            "alias_name": rec.alias_name,
            "timing": {
                "prompt_assembly_ms": round(rec.prompt_assembly_ms(), 2),
                "rag_ms": round(rec.rag_duration_ms(), 2) if rec.rag_duration_ms() else None,
                "search_ms": (
                    round(rec.search_duration_ms(), 2) if rec.search_duration_ms() else None
                ),
                "ttft_ms": round(rec.ttft_ms(), 2) if rec.ttft_ms() is not None else None,
                "stream_ms": round(rec.stream_duration_ms(), 2),
                "total_ms": round(rec.total_wall_ms(), 2),
            },
            "stop_reason": rec.stop_reason,
            "completion_tokens": rec.completion_tokens,
            "tokens_per_second": (
                round(rec.tokens_per_second, 1) if rec.tokens_per_second else None
            ),
            "usage": (
                {
                    "prompt_tokens": rec.usage.prompt_tokens,
                    "completion_tokens": rec.usage.completion_tokens,
                    "total_tokens": rec.usage.total_tokens,
                }
                if rec.usage
                else None
            ),
            "rag_query": rec.rag_query,
            "rag_chunks_injected": sum(1 for r in rec.rag_results if r.relevance >= 0.70),
            "rag_chunks_total": len(rec.rag_results),
            "tool_calls": [
                {
                    "name": tc.name,
                    "duration_s": tc.duration_s,
                    "success": tc.success,
                    "used": tc.used_in_response,
                }
                for tc in rec.tool_calls
            ],
            "agent_thinking": rec.agent_thinking if rec.agent_thinking else None,
        }

    # ── HTTP client (for API logging) ─────────────────────────────────────

    def http_client(self) -> Any:
        """Return an instrumented httpx.AsyncClient when API logging is on.

        Returns None when API logging is inactive so providers use their
        own default client.
        """
        if not self._api_logging:
            return None
        if self._http_client is None:
            try:
                from anythink.debug.http_logger import DebugHttpLogger

                logger = DebugHttpLogger()
                import httpx

                self._http_client = httpx.AsyncClient(event_hooks=logger.make_hooks())
            except ImportError:
                pass
        return self._http_client
