"""Plan Mode dataclasses — ExecutionPlan, PlanPhase, PhaseUpdate, MixingResult."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anythink.optimize.models import TurnMMOSMetadata

# ── Phase status values ───────────────────────────────────────────────────────

PHASE_STATUS_WAITING = "waiting"
PHASE_STATUS_RUNNING = "running"
PHASE_STATUS_DONE = "done"
PHASE_STATUS_FAILED = "failed"
PHASE_STATUS_SKIPPED = "skipped"

PLAN_STATUS_PENDING = "pending"
PLAN_STATUS_APPROVED = "approved"
PLAN_STATUS_RUNNING = "running"
PLAN_STATUS_DONE = "done"
PLAN_STATUS_ABORTED = "aborted"

# Estimated seconds per 1000 tokens (rough; used for time estimate)
_SECS_PER_1K_TOKENS_FAST = 2.0
_SECS_PER_1K_TOKENS_SLOW = 6.0


# ── Core dataclasses ─────────────────────────────────────────────────────────


@dataclass
class PlanPhase:
    """A single phase in an ExecutionPlan."""

    phase_num: int
    title: str
    description: str
    model_id: str
    estimated_tokens: int
    depends_on: list[int] = field(default_factory=list)
    output_type: str = "explanation"  # "explanation"|"code"|"table"|"detail"
    status: str = PHASE_STATUS_WAITING
    output: str = ""
    elapsed_s: float = 0.0
    actual_model: str = ""  # filled after execution (may differ if switched)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_num": self.phase_num,
            "title": self.title,
            "description": self.description,
            "model_id": self.model_id,
            "estimated_tokens": self.estimated_tokens,
            "depends_on": list(self.depends_on),
            "output_type": self.output_type,
            "status": self.status,
            "output": self.output,
            "elapsed_s": self.elapsed_s,
            "actual_model": self.actual_model,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanPhase:
        return cls(
            phase_num=int(data["phase_num"]),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            model_id=str(data.get("model_id", "")),
            estimated_tokens=int(data.get("estimated_tokens", 500)),
            depends_on=[int(x) for x in data.get("depends_on", [])],
            output_type=str(data.get("output_type", "explanation")),
            status=str(data.get("status", PHASE_STATUS_WAITING)),
            output=str(data.get("output", "")),
            elapsed_s=float(data.get("elapsed_s", 0.0)),
            actual_model=str(data.get("actual_model", "")),
        )


@dataclass
class ExecutionPlan:
    """A complete multi-phase execution plan."""

    plan_id: str
    session_id: str
    original_query: str
    phases: list[PlanPhase]
    created_at: datetime
    recombination_model: str
    status: str = PLAN_STATUS_PENDING
    final_output: str = ""

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def total_estimated_tokens(self) -> int:
        return sum(p.estimated_tokens for p in self.phases)

    @property
    def unique_models(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for p in self.phases:
            if p.model_id and p.model_id not in seen:
                seen.add(p.model_id)
                result.append(p.model_id)
        if self.recombination_model and self.recombination_model not in seen:
            result.append(self.recombination_model)
        return result

    @property
    def estimated_minutes(self) -> tuple[float, float]:
        """Return (min_minutes, max_minutes) estimate for plan execution."""
        total = self.total_estimated_tokens
        fast = (total / 1000) * _SECS_PER_1K_TOKENS_FAST / 60
        slow = (total / 1000) * _SECS_PER_1K_TOKENS_SLOW / 60
        return round(fast, 1), round(slow, 1)

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "session_id": self.session_id,
            "original_query": self.original_query,
            "phases": [p.to_dict() for p in self.phases],
            "created_at": self.created_at.isoformat(),
            "recombination_model": self.recombination_model,
            "status": self.status,
            "final_output": self.final_output,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionPlan:
        return cls(
            plan_id=str(data["plan_id"]),
            session_id=str(data.get("session_id", "")),
            original_query=str(data.get("original_query", "")),
            phases=[PlanPhase.from_dict(p) for p in data.get("phases", [])],
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.utcnow(),
            recombination_model=str(data.get("recombination_model", "")),
            status=str(data.get("status", PLAN_STATUS_PENDING)),
            final_output=str(data.get("final_output", "")),
        )

    # ── Text file format ──────────────────────────────────────────────────

    def to_text(self) -> str:
        """Serialise to a human-readable plan file format."""
        lines: list[str] = [
            f"PLAN: {self.plan_id}",
            f"SESSION: {self.session_id}",
            f"QUERY: {self.original_query}",
            f"CREATED: {self.created_at.isoformat()}",
            f"STATUS: {self.status}",
            f"RECOMBINATION_MODEL: {self.recombination_model}",
            "",
        ]
        for phase in self.phases:
            depends = ",".join(str(d) for d in phase.depends_on) or "none"
            lines += [
                f"PHASE {phase.phase_num}: {phase.title}",
                f"  DESCRIPTION: {phase.description}",
                f"  MODEL: {phase.model_id}",
                f"  EST_TOKENS: {phase.estimated_tokens}",
                f"  DEPENDS_ON: {depends}",
                f"  OUTPUT_TYPE: {phase.output_type}",
                f"  STATUS: {phase.status}",
                f"  ELAPSED: {phase.elapsed_s:.2f}",
                f"  ACTUAL_MODEL: {phase.actual_model}",
                "  OUTPUT:",
            ]
            for output_line in phase.output.splitlines():
                lines.append(f"    {output_line}")
            lines += ["  ---END_OUTPUT---", ""]

        lines += [
            "FINAL_OUTPUT:",
            self.final_output,
            "---END_FINAL_OUTPUT---",
        ]
        return "\n".join(lines)

    @classmethod
    def from_text(cls, text: str) -> ExecutionPlan:
        """Deserialise from the human-readable plan file format."""
        lines = text.splitlines()
        meta: dict[str, str] = {}
        phases: list[PlanPhase] = []
        final_output_lines: list[str] = []

        i = 0
        # Parse header metadata
        while i < len(lines):
            line = lines[i]
            if line.startswith("PHASE "):
                break
            if line.startswith("FINAL_OUTPUT:"):
                break
            for key in ("PLAN", "SESSION", "QUERY", "CREATED", "STATUS", "RECOMBINATION_MODEL"):
                if line.startswith(f"{key}: "):
                    meta[key] = line[len(key) + 2:]
            i += 1

        # Parse phases
        while i < len(lines):
            line = lines[i]
            if line.startswith("FINAL_OUTPUT:"):
                i += 1
                break
            if line.startswith("PHASE "):
                rest = line[6:]  # after "PHASE "
                colon_pos = rest.find(":")
                phase_num = int(rest[:colon_pos].strip()) if colon_pos > 0 else len(phases) + 1
                title = rest[colon_pos + 1:].strip() if colon_pos > 0 else rest.strip()
                phase_meta: dict[str, str] = {"title": title}
                output_lines: list[str] = []
                in_output = False
                i += 1
                while i < len(lines):
                    pline = lines[i]
                    if pline.startswith("PHASE ") or pline.startswith("FINAL_OUTPUT:"):
                        break
                    if in_output:
                        if pline.strip() == "---END_OUTPUT---":
                            in_output = False
                        else:
                            output_lines.append(pline[4:] if pline.startswith("    ") else pline)
                    else:
                        if pline.strip() == "OUTPUT:":
                            in_output = True
                        else:
                            for key in (
                                "DESCRIPTION",
                                "MODEL",
                                "EST_TOKENS",
                                "DEPENDS_ON",
                                "OUTPUT_TYPE",
                                "STATUS",
                                "ELAPSED",
                                "ACTUAL_MODEL",
                            ):
                                if pline.strip().startswith(f"{key}: "):
                                    phase_meta[key] = pline.strip()[len(key) + 2:]
                    i += 1

                depends_raw = phase_meta.get("DEPENDS_ON", "none")
                depends = (
                    []
                    if depends_raw == "none"
                    else [int(x.strip()) for x in depends_raw.split(",") if x.strip().isdigit()]
                )
                phases.append(
                    PlanPhase(
                        phase_num=phase_num,
                        title=phase_meta.get("title", ""),
                        description=phase_meta.get("DESCRIPTION", ""),
                        model_id=phase_meta.get("MODEL", ""),
                        estimated_tokens=int(phase_meta.get("EST_TOKENS", "500")),
                        depends_on=depends,
                        output_type=phase_meta.get("OUTPUT_TYPE", "explanation"),
                        status=phase_meta.get("STATUS", PHASE_STATUS_WAITING),
                        elapsed_s=float(phase_meta.get("ELAPSED", "0.0")),
                        actual_model=phase_meta.get("ACTUAL_MODEL", ""),
                        output="\n".join(output_lines),
                    )
                )
            else:
                i += 1

        # Parse final output
        while i < len(lines):
            line = lines[i]
            if line.strip() == "---END_FINAL_OUTPUT---":
                break
            final_output_lines.append(line)
            i += 1

        created_raw = meta.get("CREATED", "")
        try:
            created_at = datetime.fromisoformat(created_raw) if created_raw else datetime.utcnow()
        except ValueError:
            created_at = datetime.utcnow()

        return cls(
            plan_id=meta.get("PLAN", str(uuid.uuid4())),
            session_id=meta.get("SESSION", ""),
            original_query=meta.get("QUERY", ""),
            phases=phases,
            created_at=created_at,
            recombination_model=meta.get("RECOMBINATION_MODEL", ""),
            status=meta.get("STATUS", PLAN_STATUS_PENDING),
            final_output="\n".join(final_output_lines),
        )

    @classmethod
    def new(
        cls,
        session_id: str,
        original_query: str,
        recombination_model: str = "",
    ) -> ExecutionPlan:
        return cls(
            plan_id=str(uuid.uuid4()),
            session_id=session_id,
            original_query=original_query,
            phases=[],
            created_at=datetime.utcnow(),
            recombination_model=recombination_model,
        )


@dataclass
class PhaseUpdate:
    """Progress event emitted to the TUI during plan execution."""

    phase_num: int
    status: str  # "running" | "done" | "failed" | "queued" | "skipped"
    elapsed_s: float
    queue_wait_s: float = 0.0
    actual_model: str = ""
    error: str = ""


@dataclass
class MixingResult:
    """Result from the MixingOrchestrator for any strategy."""

    strategy: str
    outputs: list[tuple[str, str, float]]  # (model_id, text, elapsed_s)
    final_text: str
    total_tokens: int
    metadata: TurnMMOSMetadata
