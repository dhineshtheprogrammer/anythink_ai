"""Background schedule runner for Anythink.

Runs as a foreground blocking loop (``anythink scheduler start``).
Uses ``croniter`` (optional dep) to evaluate cron expressions.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from anythink.schedule.models import ScheduledPrompt

if TYPE_CHECKING:
    from anythink.app.context import AppContext

log = logging.getLogger(__name__)

# How often (in seconds) the loop wakes up to check for due schedules.
_POLL_INTERVAL_S = 60


def _is_due(schedule: ScheduledPrompt, now: datetime) -> bool:
    """Return True if *schedule* should fire given the current *now*.

    A schedule is due when either it has never run, or its most recent
    expected cron firing time falls after its last recorded run.

    ``croniter`` is imported lazily so the scheduler module is importable
    even when the package is not installed; callers catch ImportError.
    """
    if not schedule.enabled:
        return False
    try:
        from croniter import croniter

        # ``get_prev`` returns the most recent time the expression *should*
        # have fired before *now*.
        cron = croniter(schedule.cron_expr, now)
        prev: datetime = cron.get_prev(datetime)

        if schedule.last_run is None:
            return True

        # Normalise to UTC-aware for safe comparison
        last = schedule.last_run
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=UTC)

        return last < prev
    except Exception as exc:
        log.warning("Cron check failed for '%s': %s", schedule.name, exc)
        return False


class ScheduleRunner:
    """Executes due scheduled prompts using the live AppContext."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    # ── single execution ───────────────────────────────────────────────────

    async def run_once(self, schedule: ScheduledPrompt) -> str:
        """Run *schedule* immediately and return the full response text.

        Side-effects: writes to output file (if configured), sends a
        desktop notification, updates last_run in the manager.
        """
        ctx = self._ctx

        alias_name = schedule.alias or ctx.config.default_model_alias
        if not alias_name:
            raise ValueError(
                f"Schedule '{schedule.name}' has no alias and no default model is configured."
            )

        alias = ctx.model_registry.get(alias_name)
        if alias is None:
            raise ValueError(
                f"Model alias '{alias_name}' referenced by schedule '{schedule.name}' not found."
            )

        api_key = ctx.key_manager.get_key(alias.provider)
        prov_cls = ctx.provider_registry.get(alias.provider)
        if prov_cls is None:
            raise ValueError(f"Provider '{alias.provider}' is not registered.")

        provider = prov_cls(api_key=api_key)

        from anythink.providers.base import ChatMessage

        messages = [ChatMessage(role="user", content=schedule.prompt)]

        full_text = ""
        async for chunk in provider.stream_chat(
            messages, alias.model_id, gen_params=alias.gen_params
        ):
            full_text += chunk.text

        now = datetime.now(UTC)

        # Write output file if configured
        if schedule.output_file:
            out = Path(schedule.output_file)
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("a", encoding="utf-8") as f:
                f.write(f"\n\n--- {now.isoformat()} ---\n{full_text}\n")

        # Desktop notification
        ctx.notifier.notify(
            "schedule_done",
            f"Anythink — {schedule.name}",
            full_text[:120],
        )

        # Persist last_run
        ctx.schedule_manager.update_last_run(schedule.name, now)

        log.info("Schedule '%s' completed (%d chars).", schedule.name, len(full_text))
        return full_text

    # ── batch: run all due schedules ───────────────────────────────────────

    async def run_all_due(self, *, now: datetime | None = None) -> list[tuple[str, bool, str]]:
        """Check all enabled schedules and fire any that are due.

        Returns a list of ``(name, success, summary)`` tuples — one per
        schedule that was actually attempted.
        """
        now = now or datetime.now(UTC)
        schedules = self._ctx.schedule_manager.list_all()
        due = [s for s in schedules if _is_due(s, now)]

        if not due:
            return []

        results: list[tuple[str, bool, str]] = []

        async def _run(s: ScheduledPrompt) -> None:
            try:
                text = await self.run_once(s)
                results.append((s.name, True, text[:80]))
            except Exception as exc:
                log.error("Schedule '%s' failed: %s", s.name, exc)
                results.append((s.name, False, str(exc)))

        await asyncio.gather(*[_run(s) for s in due])
        return results

    # ── foreground event loop ──────────────────────────────────────────────

    async def start(self, poll_interval: int = _POLL_INTERVAL_S) -> None:
        """Block indefinitely, checking for due schedules every *poll_interval* seconds.

        This is the entry point for ``anythink scheduler start``.
        Exits cleanly on KeyboardInterrupt.
        """
        schedules = self._ctx.schedule_manager.list_all()
        enabled = sum(1 for s in schedules if s.enabled)
        print(
            f"Anythink Scheduler — {enabled} enabled schedule(s) loaded. "
            f"Checking every {poll_interval}s. Ctrl+C to stop."
        )

        try:
            while True:
                fired = await self.run_all_due()
                for name, ok, summary in fired:
                    status = "✓" if ok else "✗"
                    print(
                        f"  [{datetime.now(UTC).strftime('%H:%M:%S')}] "
                        f"{status} {name}: {summary[:60]}"
                    )

                await asyncio.sleep(poll_interval)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nScheduler stopped.")
