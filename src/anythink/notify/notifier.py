"""Notifier: best-effort cross-platform desktop notifications.

Notification types and their default enabled state:

  rag_build_done    — RAG index rebuild completed
  slow_response     — AI response took > SLOW_RESPONSE_S seconds
  exec_done         — Code execution finished (any duration)
  browse_done       — Agentic web browse completed
  provider_failure  — LLM provider returned an error

Each type can be toggled individually via the ``notifications`` dict in
``AppConfig``, or all at once via ``Notifier.set_enabled()``.
"""

from __future__ import annotations

from anythink.notify.backends import BaseNotificationBackend, detect_backend

# Per-type defaults (all on)
NOTIFICATION_DEFAULTS: dict[str, bool] = {
    "rag_build_done": True,
    "slow_response": True,
    "exec_done": True,
    "browse_done": True,
    "provider_failure": True,
    # V4 MMOS notification types
    "plan_mode_complete": True,   # fires when all Plan Mode phases + recombination finish
    "rate_limit_switch": False,   # off by default — too noisy during normal use
    "model_unavailable": True,    # fires when a model becomes unreachable in auto mode
}

SLOW_RESPONSE_S: float = 15.0  # seconds before a "slow response" notification fires
SLOW_EXEC_S: float = 10.0  # seconds before an "exec done" notification fires


class Notifier:
    """Dispatches desktop notifications to the detected platform backend.

    All delivery failures are silently swallowed — notifications must never
    interrupt the chat experience.
    """

    def __init__(
        self,
        config_toggles: dict[str, bool] | None = None,
        *,
        enabled: bool = True,
        backend: BaseNotificationBackend | None = None,
    ) -> None:
        self._enabled = enabled
        self._toggles: dict[str, bool] = {
            **NOTIFICATION_DEFAULTS,
            **(config_toggles or {}),
        }
        self._backend: BaseNotificationBackend = backend or detect_backend()

    # ── public API ─────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__

    def is_type_enabled(self, notification_type: str) -> bool:
        """Return True when *notification_type* should fire."""
        return self._enabled and self._toggles.get(notification_type, True)

    def notify(self, notification_type: str, title: str, message: str) -> None:
        """Fire a notification if *notification_type* is enabled."""
        if not self.is_type_enabled(notification_type):
            return
        import contextlib

        with contextlib.suppress(Exception):
            self._backend.send(title, message)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable all notifications globally."""
        self._enabled = enabled

    def set_type_enabled(self, notification_type: str, enabled: bool) -> None:
        """Enable or disable a single notification type."""
        self._toggles[notification_type] = enabled

    def status(self) -> dict[str, bool | str]:
        """Return a snapshot of current settings (useful for /notify status)."""
        return {
            "enabled": self._enabled,
            "backend": self.backend_name,
            **{f"type:{k}": v for k, v in self._toggles.items()},
        }
