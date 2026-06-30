"""WorkflowLogger — writes structured plain-text execution logs to disk."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from anythink.workflow.models import (
    LoopIterationRecord,
    StageResult,
    StageType,
    WorkflowLog,
    WorkflowPlan,
    WorkflowStatus,
)

_SEP = "─" * 70


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowLogger:
    """Creates and finalises :class:`WorkflowLog` objects, then serialises them
    to plain-text ``.log`` files in *log_dir*.

    File naming: ``YYYY-MM-DD_HHMMSS_<workflow-name>.log``
    """

    def __init__(self, log_dir: Path) -> None:
        self._dir = log_dir

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def begin(self, plan: WorkflowPlan) -> WorkflowLog:
        """Allocate a new :class:`WorkflowLog` for *plan*."""
        return WorkflowLog(
            workflow_name=plan.name,
            trigger=plan.trigger,
            start_time=_now_utc(),
            models_used=list(plan.models_used),
            mcp_servers_called=list(plan.mcp_servers_used),
        )

    def record_stage(self, log: WorkflowLog, result: StageResult) -> None:
        """Append *result* to *log*. Updates models/MCP server lists."""
        log.stage_records.append(result)
        if result.model_alias and result.model_alias not in log.models_used:
            log.models_used.append(result.model_alias)
        if result.tool_name:
            server = result.tool_name.split(".")[0]
            if server not in log.mcp_servers_called:
                log.mcp_servers_called.append(server)

    def record_loop_iteration(
        self,
        log: WorkflowLog,
        item_id: str,
        iteration_index: int,
        duration_s: float,
        result_summary: str,
        skipped: bool = False,
        error: str | None = None,
    ) -> None:
        log.loop_iterations.append(
            LoopIterationRecord(
                item_id=item_id,
                iteration_index=iteration_index,
                duration_s=duration_s,
                result_summary=result_summary,
                skipped=skipped,
                error=error,
            )
        )

    def finalize(
        self,
        log: WorkflowLog,
        status: WorkflowStatus,
        final_output: str,
    ) -> Path:
        """Set the terminal status and final output, write the log file, return its path."""
        log.end_time = _now_utc()
        log.status = status
        log.final_output = final_output

        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / self._filename(log)
        path.write_text(self._render(log), encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_logs(self) -> list[Path]:
        """Return all log paths sorted most-recent first."""
        if not self._dir.exists():
            return []
        return sorted(self._dir.glob("*.log"), reverse=True)

    def latest_log(self) -> Path | None:
        logs = self.list_logs()
        return logs[0] if logs else None

    # ------------------------------------------------------------------
    # Internal rendering
    # ------------------------------------------------------------------

    def _filename(self, log: WorkflowLog) -> str:
        ts = log.start_time.strftime("%Y-%m-%d_%H%M%S")
        safe_name = log.workflow_name.replace(" ", "-").replace("/", "-")[:40]
        return f"{ts}_{safe_name}.log"

    def _render(self, log: WorkflowLog) -> str:
        lines: list[str] = []

        # ── Header ───────────────────────────────────────────────────────
        lines += [
            _SEP,
            f"  Anythink Workflow Execution Log",
            _SEP,
            f"  Workflow : {log.workflow_name}",
            f"  Trigger  : {log.trigger}",
            f"  Started  : {log.start_time.isoformat()}",
            f"  Ended    : {log.end_time.isoformat() if log.end_time else 'N/A'}",
            f"  Duration : {self._duration(log)}",
            f"  Status   : {log.status.value.upper()}",
            "",
            f"  Models   : {', '.join(log.models_used) or 'none'}",
            f"  MCP      : {', '.join(log.mcp_servers_called) or 'none'}",
            _SEP,
            "",
        ]

        # ── Per-stage blocks ─────────────────────────────────────────────
        for i, result in enumerate(log.stage_records, start=1):
            lines += self._render_stage(i, result)

        # ── Loop summary ─────────────────────────────────────────────────
        if log.loop_iterations:
            lines += self._render_loop_summary(log)

        # ── Error blocks ─────────────────────────────────────────────────
        errors = [r for r in log.stage_records if r.error]
        if errors:
            lines += [_SEP, "  ERRORS", _SEP, ""]
            for r in errors:
                lines += [
                    f"  Stage {r.stage_id} ({r.stage_type.value})",
                    f"  Error : {r.error}",
                    f"  Fallback used : {r.fallback_used}",
                    "",
                ]

        # ── Final output ─────────────────────────────────────────────────
        lines += [
            _SEP,
            "  FINAL OUTPUT",
            _SEP,
            "",
            log.final_output or "(no output)",
            "",
            _SEP,
        ]

        return "\n".join(lines)

    def _duration(self, log: WorkflowLog) -> str:
        if not log.end_time:
            return "N/A"
        delta = log.end_time - log.start_time
        total = int(delta.total_seconds())
        m, s = divmod(total, 60)
        return f"{m}m {s}s"

    def _render_stage(self, index: int, result: StageResult) -> list[str]:
        lines: list[str] = [
            f"  Stage {index} · {result.stage_id} · {result.stage_type.value}",
            f"  {_SEP[:60]}",
        ]

        if result.stage_type == StageType.LLM_SPECIALIST:
            lines.append(f"  Model  : {result.model_alias or 'unknown'}")
            if result.fallback_used:
                lines.append(f"  Fallback chain : {' → '.join(result.fallback_chain)}")
        elif result.stage_type == StageType.MCP_CALL:
            lines.append(f"  Tool   : {result.tool_name or 'unknown'}")

        lines.append(f"  Duration : {result.duration_s:.2f}s")

        if result.skipped:
            lines.append("  [SKIPPED]")
        if result.user_decision:
            lines.append(f"  User decision : {result.user_decision.value}")
        if result.error:
            lines.append(f"  ERROR : {result.error}")

        if result.raw_content:
            lines += ["", "  Output:", ""]
            for line in result.raw_content.splitlines():
                lines.append(f"    {line}")

        lines += ["", ""]
        return lines

    def _render_loop_summary(self, log: WorkflowLog) -> list[str]:
        total = len(log.loop_iterations)
        completed = sum(1 for li in log.loop_iterations if not li.skipped and not li.error)
        skipped = sum(1 for li in log.loop_iterations if li.skipped)
        failed = sum(1 for li in log.loop_iterations if li.error)

        lines: list[str] = [
            _SEP,
            "  LOOP SUMMARY",
            _SEP,
            "",
            f"  Total iterations : {total}",
            f"  Completed        : {completed}",
            f"  Skipped          : {skipped}",
            f"  Failed           : {failed}",
            "",
        ]
        for li in log.loop_iterations:
            status = "SKIP" if li.skipped else ("FAIL" if li.error else "OK  ")
            lines.append(
                f"  [{status}] #{li.iteration_index + 1:>3}  {li.item_id:<30}"
                f"  {li.duration_s:.2f}s  {li.result_summary[:60]}"
            )
        lines += ["", ""]
        return lines
