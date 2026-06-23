"""Rate limit queue manager — per-model RPM/TPM/RPD counters and auto-switching."""

from __future__ import annotations

import datetime as _dt
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anythink.optimize.registry import ModelCapabilityRegistry


@dataclass
class ModelRateWindow:
    """Live rate-limit counters for a single model within the current session."""

    model_id: str
    requests_in_window: int = 0
    tokens_in_window: int = 0
    requests_today: int = 0
    window_start: float = field(default_factory=time.monotonic)
    day_start: float = field(default_factory=time.monotonic)
    unavailable: bool = False  # True when marked unreachable (network failure)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "requests_in_window": self.requests_in_window,
            "tokens_in_window": self.tokens_in_window,
            "requests_today": self.requests_today,
            "window_start": self.window_start,
            "day_start": self.day_start,
            "unavailable": self.unavailable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRateWindow:
        return cls(
            model_id=str(data["model_id"]),
            requests_in_window=int(data.get("requests_in_window", 0)),
            tokens_in_window=int(data.get("tokens_in_window", 0)),
            requests_today=int(data.get("requests_today", 0)),
            window_start=float(data.get("window_start", time.monotonic())),
            day_start=float(data.get("day_start", time.monotonic())),
            unavailable=bool(data.get("unavailable", False)),
        )


_WINDOW_SECONDS = 60.0
_DAY_SECONDS = 86400.0


class RateLimitManager:
    """Tracks and enforces per-model rate limits (RPM, TPM, RPD).

    State is ephemeral in-memory and optionally persisted to rate_limit_state.json
    for cross-restart continuity within the same day. Counters auto-reset at
    the appropriate window boundary.
    """

    def __init__(self, state_path: Path, registry: ModelCapabilityRegistry) -> None:
        self._state_path = state_path
        self._registry = registry
        self._windows: dict[str, ModelRateWindow] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        if not self._state_path.exists():
            return

        try:
            raw: dict[str, Any] = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        now = time.monotonic()
        for entry in raw.get("windows", []):
            try:
                window = ModelRateWindow.from_dict(entry)
                # Drop stale day windows (older than 24h)
                if now - window.day_start < _DAY_SECONDS:
                    self._windows[window.model_id] = window
            except (KeyError, ValueError):
                continue

    def _get_window(self, model_id: str) -> ModelRateWindow:
        self._load()
        if model_id not in self._windows:
            self._windows[model_id] = ModelRateWindow(model_id=model_id)
        window = self._windows[model_id]
        now = time.monotonic()

        # Reset 60-second window if expired
        if now - window.window_start >= _WINDOW_SECONDS:
            window.requests_in_window = 0
            window.tokens_in_window = 0
            window.window_start = now

        # Reset day window if expired
        if now - window.day_start >= _DAY_SECONDS:
            window.requests_today = 0
            window.day_start = now

        return window

    # ── Public API ────────────────────────────────────────────────────────

    def record_request(self, model_id: str, tokens: int) -> None:
        window = self._get_window(model_id)
        window.requests_in_window += 1
        window.tokens_in_window += tokens
        window.requests_today += 1

    def is_at_rpm_limit(self, model_id: str) -> bool:
        cap = self._registry.get(model_id)
        if cap is None or cap.rpm_limit is None:
            return False
        window = self._get_window(model_id)
        return window.requests_in_window >= cap.rpm_limit

    def is_at_tpm_limit(self, model_id: str, estimated_tokens: int) -> bool:
        cap = self._registry.get(model_id)
        if cap is None or cap.tpm_limit is None:
            return False
        window = self._get_window(model_id)
        return (window.tokens_in_window + estimated_tokens) > cap.tpm_limit

    def is_at_rpd_limit(self, model_id: str) -> bool:
        cap = self._registry.get(model_id)
        if cap is None or cap.rpd_limit is None:
            return False
        window = self._get_window(model_id)
        return window.requests_today >= cap.rpd_limit

    def seconds_until_available(self, model_id: str) -> float:
        window = self._get_window(model_id)
        now = time.monotonic()
        remaining = _WINDOW_SECONDS - (now - window.window_start)
        return max(0.0, remaining)

    def get_status(self) -> list[ModelRateWindow]:
        self._load()
        # Ensure windows exist for all registered models
        for cap in self._registry.all():
            self._get_window(cap.id)
        return list(self._windows.values())

    def find_next_available(self, candidates: list[str]) -> str | None:
        """Return the first candidate model that is not at any rate limit."""
        for model_id in candidates:
            window = self._get_window(model_id)
            if window.unavailable:
                continue
            if self.is_at_rpm_limit(model_id):
                continue
            if self.is_at_rpd_limit(model_id):
                continue
            return model_id
        return None

    def mark_unavailable(self, model_id: str) -> None:
        """Flag a model as network-unavailable for the rest of the session."""
        window = self._get_window(model_id)
        window.unavailable = True

    def reset_counters(self) -> None:
        """Reset all in-memory counters and delete the state file."""
        self._windows.clear()
        if self._state_path.exists():
            self._state_path.unlink(missing_ok=True)

    def save(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "saved_at": _dt.datetime.now(tz=_dt.UTC).isoformat(),
            "windows": [w.to_dict() for w in self._windows.values()],
        }
        self._state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
