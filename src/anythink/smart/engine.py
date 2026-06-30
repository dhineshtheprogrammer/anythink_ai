"""SmartEngine — main MMAE pipeline orchestrator."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from anythink.providers.base import ChatMessage
from anythink.smart.combiner import CombinerModel
from anythink.smart.detector import detect_format
from anythink.smart.executor import SequentialExecutor
from anythink.smart.formatter import FormatterModel
from anythink.smart.models import SmartResult, TemporaryStore
from anythink.smart.quality import QualityGate
from anythink.smart.router import RouterModel
from anythink.smart.store import TemporaryResponseStore

if TYPE_CHECKING:
    from anythink.config.models import ModelRegistry
    from anythink.debug.manager import DebugManager
    from anythink.keys.manager import KeyManager
    from anythink.providers.registry import ProviderRegistry
    from anythink.smart.registry import SmartRegistry
    from anythink.spend.tracker import SpendTracker


class SmartEngine:
    """Orchestrates the full MMAE pipeline for one conversational turn.

    Pipeline:
      1. detect_format(message)
      2. RouterModel.route()          → RoutingPlan
      3. SequentialExecutor.execute() → fills TemporaryResponseStore
      4. CombinerModel.combine()      → combined_text
      5. FormatterModel.format()      → final_text  (only when format requested)
    """

    def __init__(
        self,
        registry: SmartRegistry,
        provider_registry: ProviderRegistry,
        model_registry: ModelRegistry,
        key_manager: KeyManager,
        debug_manager: DebugManager,
        spend_tracker: SpendTracker,
        quality_threshold: int = 50,
        max_splits: int = 5,
    ) -> None:
        self._registry = registry
        self._debug_manager = debug_manager
        self._spend_tracker = spend_tracker

        gate = QualityGate(threshold=quality_threshold)
        self._router = RouterModel(
            registry=registry,
            provider_registry=provider_registry,
            model_registry=model_registry,
            key_manager=key_manager,
            max_splits=max_splits,
        )
        self._store = TemporaryResponseStore()
        self._executor = SequentialExecutor(
            registry=registry,
            quality_gate=gate,
            provider_registry=provider_registry,
            model_registry=model_registry,
            key_manager=key_manager,
        )
        self._combiner = CombinerModel(
            registry=registry,
            provider_registry=provider_registry,
            model_registry=model_registry,
            key_manager=key_manager,
        )
        self._formatter = FormatterModel(
            registry=registry,
            provider_registry=provider_registry,
            model_registry=model_registry,
            key_manager=key_manager,
        )

    async def run(
        self,
        message: str,
        history: list[ChatMessage],
        session_id: str,
        combiner_mode: str = "stitch",
        session_format: str = "",
        on_progress: Callable[[str], None] | None = None,
    ) -> SmartResult:
        """Execute the full MMAE pipeline and return a SmartResult."""
        t_start = time.monotonic()

        # 1. Detect explicit format request in the message
        format_hint = detect_format(message) or (session_format or None)
        active_format = format_hint

        # 2. Router
        self._emit_debug("[SMART] Router invoked", level=1)
        routing_plan = await self._router.route(message, history, format_hint)
        n_cats = len(routing_plan.categories_detected)
        self._emit_debug(
            f"[SMART] Categories detected: {', '.join(routing_plan.categories_detected)}",
            detail=f"complexity={routing_plan.complexity}  n={n_cats}",
            level=2,
        )
        self._emit_debug(
            "[SMART] Routing reasoning",
            detail=routing_plan.reasoning_summary,
            level=3,
        )

        # 3. Execute specialists sequentially
        self._store.clear()

        def _progress(msg: str, current: int, total: int) -> None:
            self._emit_debug(
                f"[SMART] Specialist {current}/{total}: {msg}",
                level=2,
            )
            if on_progress:
                with contextlib.suppress(Exception):
                    on_progress(msg)

        await self._executor.execute(
            routing_plan=routing_plan,
            original_message=message,
            history=history,
            store=self._store,
            on_progress=_progress,
        )

        # Emit per-specialist quality details
        for entry in self._store.all():
            flag = " ⚠ LOW CONFIDENCE" if entry.low_confidence else " PASS"
            self._emit_debug(
                f"[SMART] Quality: slot {entry.slot} ({entry.category})",
                detail=f"score={entry.quality_score}  retries={entry.retry_count}{flag}",
                level=2,
            )

        # 4. Combine
        combiner_model_name = self._combiner.combiner_alias_name()
        self._emit_debug(
            "[SMART] Combiner invoked",
            detail=f"model={combiner_model_name}  mode={combiner_mode}",
            level=2,
        )
        combined_text = await self._combiner.combine(self._store, combiner_mode)

        # 5. Format (only when requested)
        formatter_applied: str | None = None
        final_text = combined_text
        if active_format:
            self._emit_debug(
                "[SMART] Formatter invoked",
                detail=f"format={active_format}",
                level=2,
            )
            final_text = await self._formatter.format(combined_text, active_format)
            formatter_applied = active_format

        total_duration_s = time.monotonic() - t_start
        self._emit_debug(
            "[SMART] Complete",
            detail=f"total={total_duration_s:.2f}s  specialists={len(self._store)}",
            level=1,
        )

        # Record synthetic spend for this turn (per-call spend is recorded inside each component)
        # We log the total at session level for /cost reporting
        self._record_session_spend(session_id, total_duration_s)

        store_snapshot = TemporaryStore(entries=self._store.all())
        return SmartResult(
            combined_text=final_text,
            formatter_applied=formatter_applied,
            total_duration_s=total_duration_s,
            routing_plan=routing_plan,
            store=store_snapshot,
            combiner_model=combiner_model_name,
            combiner_mode=combiner_mode,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_debug(
        self,
        label: str,
        detail: str = "",
        level: int = 2,
    ) -> None:
        """Emit a debug event if debug mode is active at the given level."""
        dm = self._debug_manager
        if dm.is_active() and dm.level() >= level:
            # Store in debug manager's pending record if one exists
            # Otherwise just mark in-memory (panel receives events via the TUI worker)
            with contextlib.suppress(AttributeError):
                dm._pending_event(label, detail)  # type: ignore[attr-defined]

    def _record_session_spend(self, session_id: str, _duration: float) -> None:
        """No-op placeholder — per-call spend is recorded by individual components."""
        pass

    def store_snapshot(self) -> TemporaryResponseStore:
        """Return a snapshot of the current store (for UI access after run())."""
        return self._store
