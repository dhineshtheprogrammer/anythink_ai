"""Core dataclasses for the Multi-Model Workflow Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class StageType(str, Enum):
    """The execution type of a single pipeline stage."""

    PLANNER = "PLANNER"
    MCP_CALL = "MCP_CALL"
    LLM_SPECIALIST = "LLM_SPECIALIST"
    USER_APPROVAL = "USER_APPROVAL"
    CONDITION = "CONDITION"
    FORMATTER = "FORMATTER"
    LOOP = "LOOP"


# Aliases for common model-output variants of stage type names.
# Small models may drop underscores, abbreviate, or output the pipe-separated
# schema hint as a literal value — these mappings handle all observed cases.
_STAGE_TYPE_ALIASES: dict[str, str] = {
    "MCP": "MCP_CALL",
    "MCP CALL": "MCP_CALL",
    "LLM": "LLM_SPECIALIST",
    "LLM SPECIALIST": "LLM_SPECIALIST",
    "LLMSPECIALIST": "LLM_SPECIALIST",
    "SPECIALIST": "LLM_SPECIALIST",
    "USER": "USER_APPROVAL",
    "USER APPROVAL": "USER_APPROVAL",
    "USERAPPROVAL": "USER_APPROVAL",
    "APPROVAL": "USER_APPROVAL",
    "COND": "CONDITION",
    "FORMAT": "FORMATTER",
    "PLAN": "PLANNER",
}

_VALID_STAGE_TYPES: frozenset[str] = frozenset(t.value for t in StageType)


def _normalize_stage_type(raw: str) -> str:
    """Coerce a model-generated type string to a canonical StageType value.

    Handles: pipe-separated schema hints, missing underscores, abbreviations,
    and mixed case — all produced by small local models that misread the schema.
    """
    # If the model output the whole pipe-separated enum hint, take the first token
    if "|" in raw:
        raw = raw.split("|")[0]

    normalized = raw.strip().upper().replace(" ", "_").replace("-", "_")

    if normalized in _VALID_STAGE_TYPES:
        return normalized

    # Try alias table (before and after underscore normalisation)
    raw_upper = raw.strip().upper()
    for variant in (raw_upper, raw_upper.replace("_", " ")):
        if variant in _STAGE_TYPE_ALIASES:
            return _STAGE_TYPE_ALIASES[variant]

    # Prefix match as last resort (e.g. "MCP_CALL_SOMETHING" → "MCP_CALL")
    for valid in _VALID_STAGE_TYPES:
        if normalized.startswith(valid):
            return valid

    return normalized  # Return as-is; StageType() will raise a clear ValueError


class AccumulationStrategy(str, Enum):
    APPEND = "append"
    MERGE = "merge"
    STRUCTURED_LIST = "structured_list"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class UserDecision(str, Enum):
    APPROVED = "approved"
    SKIPPED = "skipped"
    ABORTED = "aborted"


# ---------------------------------------------------------------------------
# Stage sub-structures
# ---------------------------------------------------------------------------


@dataclass
class LoopDefinition:
    """Configuration for a LOOP stage."""

    input_collection_ref: str
    """Dot-path reference to the input collection, e.g. 'stage_1.email_list'."""

    sub_stages: list[Stage] = field(default_factory=list)
    """The stages to execute for each item in the collection."""

    accumulation_strategy: AccumulationStrategy = AccumulationStrategy.APPEND

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_collection_ref": self.input_collection_ref,
            "sub_stages": [s.to_dict() for s in self.sub_stages],
            "accumulation_strategy": self.accumulation_strategy.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopDefinition:
        return cls(
            input_collection_ref=data["input_collection_ref"],
            sub_stages=[Stage.from_dict(s) for s in data.get("sub_stages", [])],
            accumulation_strategy=AccumulationStrategy(
                data.get("accumulation_strategy", "append")
            ),
        )


@dataclass
class Stage:
    """A single step in a workflow pipeline."""

    id: str
    """Unique identifier within the plan, e.g. 'stage_1', 'stage_2a'."""

    type: StageType
    label: str = ""
    """Short human-readable display label."""

    # LLM_SPECIALIST fields
    model_alias: str = ""
    """Model alias to invoke for LLM_SPECIALIST stages."""

    task_instruction: str = ""
    """What the specialist model is being asked to do with its input."""

    # MCP_CALL fields
    tool_name: str = ""
    """Fully-qualified tool name, e.g. 'gmail.list_inbox'."""

    tool_params: dict[str, Any] = field(default_factory=dict)
    """Static or template parameters for the MCP tool call."""

    # Data flow
    output_field: str = ""
    """Named key under which this stage's output is stored, e.g. 'email_list'."""

    input_refs: list[str] = field(default_factory=list)
    """Dot-path references to upstream outputs, e.g. ['stage_1.email_list']."""

    # FORMATTER fields
    expected_format: str = ""
    """Target format: 'markdown' | 'plain_text' | 'json' | 'csv' | 'html' | 'numbered_list'."""

    # CONDITION fields
    condition_expr: str = ""
    """Boolean expression evaluated against accumulated_results."""

    branch_a: list[Stage] = field(default_factory=list)
    """Stages executed when condition_expr is True."""

    branch_b: list[Stage] = field(default_factory=list)
    """Stages executed when condition_expr is False."""

    # LOOP fields
    loop_def: LoopDefinition | None = None

    # USER_APPROVAL fields
    approval_message: str = ""
    """Message shown to the user at the approval gate."""

    # Guards
    is_destructive: bool = False
    """Always triggers a USER_APPROVAL guard before execution."""

    is_parallel: bool = False
    """When True this stage runs concurrently with sibling parallel stages."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "label": self.label,
            "model_alias": self.model_alias,
            "task_instruction": self.task_instruction,
            "tool_name": self.tool_name,
            "tool_params": self.tool_params,
            "output_field": self.output_field,
            "input_refs": self.input_refs,
            "expected_format": self.expected_format,
            "condition_expr": self.condition_expr,
            "branch_a": [s.to_dict() for s in self.branch_a],
            "branch_b": [s.to_dict() for s in self.branch_b],
            "loop_def": self.loop_def.to_dict() if self.loop_def else None,
            "approval_message": self.approval_message,
            "is_destructive": self.is_destructive,
            "is_parallel": self.is_parallel,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], _index: int = 0) -> Stage:
        loop_raw = data.get("loop_def")
        raw_id = data.get("id") or data.get("stage_id") or f"stage_{_index + 1}"
        raw_type = data.get("type") or data.get("stage_type") or "LLM_SPECIALIST"
        return cls(
            id=str(raw_id),
            type=StageType(_normalize_stage_type(str(raw_type))),
            label=data.get("label", ""),
            model_alias=data.get("model_alias", ""),
            task_instruction=data.get("task_instruction", ""),
            tool_name=data.get("tool_name", ""),
            tool_params=data.get("tool_params", {}),
            output_field=data.get("output_field", ""),
            input_refs=data.get("input_refs", []),
            expected_format=data.get("expected_format", ""),
            condition_expr=data.get("condition_expr", ""),
            branch_a=[Stage.from_dict(s) for s in data.get("branch_a", [])],
            branch_b=[Stage.from_dict(s) for s in data.get("branch_b", [])],
            loop_def=LoopDefinition.from_dict(loop_raw) if loop_raw else None,
            approval_message=data.get("approval_message", ""),
            is_destructive=data.get("is_destructive", False),
            is_parallel=data.get("is_parallel", False),
        )


# ---------------------------------------------------------------------------
# Workflow plan
# ---------------------------------------------------------------------------


@dataclass
class WorkflowPlan:
    """The complete parsed plan produced by the planner model."""

    name: str
    """Workflow name — either user-supplied or auto-generated."""

    trigger: str
    """The original user task description."""

    stages: list[Stage] = field(default_factory=list)
    models_used: list[str] = field(default_factory=list)
    mcp_servers_used: list[str] = field(default_factory=list)
    estimated_duration_s: int | None = None
    estimated_loop_iterations: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "trigger": self.trigger,
            "stages": [s.to_dict() for s in self.stages],
            "models_used": self.models_used,
            "mcp_servers_used": self.mcp_servers_used,
            "estimated_duration_s": self.estimated_duration_s,
            "estimated_loop_iterations": self.estimated_loop_iterations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowPlan:
        raw_name = data.get("name") or data.get("workflow_name") or "unnamed-workflow"
        return cls(
            name=str(raw_name),
            trigger=data.get("trigger", ""),
            stages=[Stage.from_dict(s, i) for i, s in enumerate(data.get("stages", []))],
            models_used=data.get("models_used", []),
            mcp_servers_used=data.get("mcp_servers_used", []),
            estimated_duration_s=data.get("estimated_duration_s"),
            estimated_loop_iterations=data.get("estimated_loop_iterations"),
        )


# ---------------------------------------------------------------------------
# Execution results
# ---------------------------------------------------------------------------


@dataclass
class StageResult:
    """Output produced by executing one stage."""

    stage_id: str
    stage_type: StageType

    output: dict[str, Any] = field(default_factory=dict)
    """Named output fields available to downstream stages."""

    raw_content: str = ""
    """Full unprocessed output text."""

    duration_s: float = 0.0
    model_alias: str = ""
    tool_name: str = ""
    fallback_used: bool = False
    fallback_chain: list[str] = field(default_factory=list)
    error: str | None = None
    skipped: bool = False
    user_decision: UserDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "stage_type": self.stage_type.value,
            "output": self.output,
            "raw_content": self.raw_content,
            "duration_s": self.duration_s,
            "model_alias": self.model_alias,
            "tool_name": self.tool_name,
            "fallback_used": self.fallback_used,
            "fallback_chain": self.fallback_chain,
            "error": self.error,
            "skipped": self.skipped,
            "user_decision": self.user_decision.value if self.user_decision else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageResult:
        ud = data.get("user_decision")
        return cls(
            stage_id=data["stage_id"],
            stage_type=StageType(data["stage_type"]),
            output=data.get("output", {}),
            raw_content=data.get("raw_content", ""),
            duration_s=data.get("duration_s", 0.0),
            model_alias=data.get("model_alias", ""),
            tool_name=data.get("tool_name", ""),
            fallback_used=data.get("fallback_used", False),
            fallback_chain=data.get("fallback_chain", []),
            error=data.get("error"),
            skipped=data.get("skipped", False),
            user_decision=UserDecision(ud) if ud else None,
        )


# ---------------------------------------------------------------------------
# Live execution state
# ---------------------------------------------------------------------------


@dataclass
class WorkflowState:
    """Mutable state tracked throughout a running workflow."""

    plan: WorkflowPlan
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_stage_id: str = ""
    completed_stages: list[StageResult] = field(default_factory=list)
    loop_position: int = 0
    loop_total: int = 0
    accumulated_results: dict[str, Any] = field(default_factory=dict)
    """Maps 'stage_id.field_name' → value for downstream references."""

    paused: bool = False
    stop_requested: bool = False

    def resolve_ref(self, ref: str) -> Any:
        """Resolve a dot-path reference such as 'stage_1.email_list'."""
        return self.accumulated_results.get(ref)

    def store_result(self, result: StageResult) -> None:
        """Store a completed stage result and index its output fields."""
        self.completed_stages.append(result)
        for key, value in result.output.items():
            self.accumulated_results[f"{result.stage_id}.{key}"] = value
        # Also store under the stage's output_field for convenience
        stage = self._find_stage(result.stage_id)
        if stage and stage.output_field:
            self.accumulated_results[stage.output_field] = result.output

    def _find_stage(self, stage_id: str) -> Stage | None:
        return next((s for s in self.plan.stages if s.id == stage_id), None)


# ---------------------------------------------------------------------------
# Execution log
# ---------------------------------------------------------------------------


@dataclass
class LoopIterationRecord:
    """Summary of one loop iteration for the execution log."""

    item_id: str
    iteration_index: int
    duration_s: float
    result_summary: str
    skipped: bool = False
    error: str | None = None


@dataclass
class WorkflowLog:
    """Complete record of one workflow execution, written to disk on finish."""

    workflow_name: str
    trigger: str
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime | None = None
    status: WorkflowStatus = WorkflowStatus.RUNNING
    stage_records: list[StageResult] = field(default_factory=list)
    loop_iterations: list[LoopIterationRecord] = field(default_factory=list)
    final_output: str = ""
    models_used: list[str] = field(default_factory=list)
    mcp_servers_called: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_name": self.workflow_name,
            "trigger": self.trigger,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value,
            "stage_records": [r.to_dict() for r in self.stage_records],
            "loop_iterations": [
                {
                    "item_id": li.item_id,
                    "iteration_index": li.iteration_index,
                    "duration_s": li.duration_s,
                    "result_summary": li.result_summary,
                    "skipped": li.skipped,
                    "error": li.error,
                }
                for li in self.loop_iterations
            ],
            "final_output": self.final_output,
            "models_used": self.models_used,
            "mcp_servers_called": self.mcp_servers_called,
        }


# ---------------------------------------------------------------------------
# Planner output variants
# ---------------------------------------------------------------------------


@dataclass
class ClarificationRequest:
    """Returned by the planner instead of a plan when the task is ambiguous."""

    questions: list[str]
    round: int = 1
    """Clarification round (1 or 2). After round 2 the planner produces a partial plan."""


# ---------------------------------------------------------------------------
# Callback protocol for engine ↔ TUI communication
# ---------------------------------------------------------------------------


@dataclass
class WorkflowCallbacks:
    """Async hooks the engine calls to communicate with the TUI/CLI layer."""

    on_stage_start: Callable[[Stage], Awaitable[None]]
    on_stage_complete: Callable[[Stage, StageResult], Awaitable[None]]
    on_approval_needed: Callable[[str], Awaitable[str]]
    """Called for USER_APPROVAL stages. Returns 'approved' | 'skipped' | 'aborted'."""

    on_loop_progress: Callable[[int, int, StageResult], Awaitable[None]]
    """Called after each loop iteration with (current, total, last_result)."""

    on_model_unavailable: Callable[[Stage, list[str]], Awaitable[str]]
    """Called when all fallbacks are exhausted. Returns an alias chosen by the user."""
