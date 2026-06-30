"""WorkflowPlanner — invokes an LLM to decompose a task into a WorkflowPlan."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from anythink.exceptions import WorkflowPlanError
from anythink.providers.base import ChatMessage, GenerationParams
from anythink.workflow.models import (
    ClarificationRequest,
    LoopDefinition,
    Stage,
    StageType,
    WorkflowPlan,
)

if TYPE_CHECKING:
    from anythink.config.models import ModelAlias, ModelRegistry
    from anythink.keys.manager import KeyManager
    from anythink.providers.registry import ProviderRegistry
    from anythink.workflow.manifest import CapabilityManifest
    from anythink.workflow.registry import WorkflowCapabilityRegistry

# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

_ROLE_DEFINITION = """\
You are the Anythink Workflow Planner. Your ONLY job is to decompose a user
task into a structured multi-stage pipeline called a WorkflowPlan.

RULES:
- You may ONLY use models, tools, and capabilities listed in the Capability
  Manifest below. Do not reference anything not in the manifest.
- Assign the most appropriate model alias to every LLM_SPECIALIST stage based
  on its capability tags.
- Insert a USER_APPROVAL stage before ANY destructive MCP tool call.
- To fetch or retrieve data (list files, read a file, call an API) use MCP_CALL.
  MCP_CALL is a single tool call — do NOT wrap it in a LOOP.
- Use a LOOP stage ONLY when you must run sub-stages once per item in a
  collection that was already fetched by a prior MCP_CALL or LLM_SPECIALIST
  stage. A LOOP stage must always follow a stage that produces the collection.
  A LOOP stage by itself with no prior stage is always wrong.
- Use parallel branches when sub-tasks are independent of each other.
- If the task is ambiguous in a way that would produce significantly different
  plans, output a clarification request instead of a plan.
- Never synthesise a final answer yourself — only produce a plan.
"""

_OUTPUT_SCHEMA = """\
OUTPUT FORMAT — respond with ONLY valid JSON, no markdown, no code fences.

The "type" field of every stage MUST be exactly one of these seven strings:
  PLANNER
  MCP_CALL
  LLM_SPECIALIST
  USER_APPROVAL
  CONDITION
  FORMATTER
  LOOP

Shape 1 — when the task is ambiguous, return this:
{
  "clarification_needed": true,
  "questions": ["Question 1?", "Question 2?"]
}

Shape 2 — when you can produce a full plan, return this:
{
  "clarification_needed": false,
  "name": "short-workflow-name",
  "trigger": "<original task text>",
  "stages": [
    {
      "id": "stage_1",
      "type": "LLM_SPECIALIST",
      "label": "Human-readable label",
      "model_alias": "",
      "task_instruction": "",
      "tool_name": "",
      "tool_params": {},
      "output_field": "result",
      "input_refs": [],
      "expected_format": "",
      "condition_expr": "",
      "branch_a": [],
      "branch_b": [],
      "loop_def": null,
      "approval_message": "",
      "is_destructive": false,
      "is_parallel": false
    }
  ],
  "models_used": [],
  "mcp_servers_used": [],
  "estimated_duration_s": null,
  "estimated_loop_iterations": null
}

STAGE TYPE DETAILS:

MCP_CALL — calls one MCP tool. Example that lists a directory:
  {"id": "stage_1", "type": "MCP_CALL", "label": "List files", "tool_name": "filesystem.list_dir",
   "tool_params": {"path": "/some/path"}, "output_field": "file_list", "input_refs": [],
   "model_alias": "", "task_instruction": "", "expected_format": "", "condition_expr": "",
   "branch_a": [], "branch_b": [], "loop_def": null, "approval_message": "",
   "is_destructive": false, "is_parallel": false}

LLM_SPECIALIST — sends text to a model. Fill model_alias and task_instruction.
  Use input_refs to reference prior stage outputs, e.g. ["stage_1.file_list"].

LOOP — runs sub_stages once per item in a prior stage's output collection.
  loop_def: {"input_collection_ref": "stage_1.file_list", "sub_stages": [...], "accumulation_strategy": "append"}
  WARNING: LOOP requires input_collection_ref to reference a prior stage output field.
  Never use LOOP as the first stage. Never use LOOP just to retrieve data.

CONDITION — evaluates condition_expr (e.g. "stage_1.count > 0") and runs branch_a (true) or branch_b (false).
USER_APPROVAL — pauses for user confirmation. Fill approval_message.
FORMATTER — converts content to a format. Fill expected_format: markdown, plain_text, json, csv, html, numbered_list.

Set unused fields to empty string "", empty list [], or null.

Set unused fields to empty string "", empty list [], or null.
"""


def _build_system_prompt(manifest_text: str) -> str:
    return "\n\n".join([_ROLE_DEFINITION, manifest_text, _OUTPUT_SCHEMA])


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_json(text: str) -> str:
    """Return the first JSON object found in *text*, stripping markdown fences."""
    # Try fenced code blocks first
    m = _JSON_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()

    # Find the outermost { … } in the raw text
    start = text.find("{")
    if start == -1:
        return text.strip()

    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return text[start:].strip()


def _repair_plan_data(data: dict[str, Any]) -> dict[str, Any]:
    """Normalise a raw planner dict so that from_dict() can always succeed.

    Small models frequently omit or rename required fields.  This function
    patches the dict in-place (on a shallow copy) rather than relying on every
    from_dict path to handle every possible omission.
    """
    data = dict(data)

    # Top-level required fields
    if not data.get("name"):
        data["name"] = "unnamed-workflow"
    if not data.get("trigger"):
        data["trigger"] = ""

    # Stages must be a list of dicts
    raw_stages = data.get("stages") or data.get("pipeline") or data.get("steps") or []
    if not isinstance(raw_stages, list):
        raw_stages = []

    repaired: list[dict[str, Any]] = []
    for i, stage in enumerate(raw_stages):
        if not isinstance(stage, dict):
            continue
        stage = dict(stage)
        # id — most common omission
        if not stage.get("id") and not stage.get("stage_id"):
            stage["id"] = f"stage_{i + 1}"
        # type — default to LLM_SPECIALIST when absent
        if not stage.get("type") and not stage.get("stage_type"):
            stage["type"] = "LLM_SPECIALIST"
        # tool_params must be a dict
        if not isinstance(stage.get("tool_params"), dict):
            stage["tool_params"] = {}
        repaired.append(stage)

    data["stages"] = repaired
    data["stages"] = _drop_spurious_loops(data["stages"])
    return data


def _has_item_ref(stage: dict[str, Any]) -> bool:
    """Return True if any string field in *stage* contains an unresolvable ``{{item}}`` ref.

    Stages with ``{{item}}`` in their params are loop sub-stages that the model
    accidentally placed at the top level. They cannot run correctly there.
    """
    def _check(val: Any) -> bool:
        if isinstance(val, str):
            return "{{item}}" in val or "{{loop." in val
        if isinstance(val, dict):
            return any(_check(v) for v in val.values())
        if isinstance(val, list):
            return any(_check(v) for v in val)
        return False

    return any(_check(v) for v in stage.values())


def _drop_spurious_loops(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove LOOP stages that immediately follow an MCP_CALL.

    Small models produce this pattern when asked to "list files" — they wrap a
    directory-listing string inside a LOOP, which is always wrong because
    ``list_dir`` returns a formatted text block, not a Python list.

    Also drops any top-level stages that contain ``{{item}}`` — these are loop
    sub-stages the model accidentally placed outside the LOOP and they can never
    run correctly at the top level.
    """
    if len(stages) < 2:
        return stages

    filtered: list[dict[str, Any]] = []
    prev_was_mcp = False

    for stage in stages:
        stype = str(stage.get("type") or stage.get("stage_type") or "").upper()

        if stype in {"MCP_CALL", "MCP"}:
            filtered.append(stage)
            prev_was_mcp = True
            continue

        if stype == "LOOP" and prev_was_mcp:
            # A LOOP immediately after an MCP_CALL is almost always a small-model
            # mistake for retrieval tasks (list_dir, read_file, API calls).
            # Drop the whole LOOP and its sub-stages — they use {{item}} which
            # is only meaningful inside a running loop executor, not at top level.
            prev_was_mcp = False
            continue

        prev_was_mcp = False
        filtered.append(stage)

    # Additionally remove any top-level stage that references {{item}} or
    # {{loop.*}} — these are displaced loop sub-stages and will always fail.
    return [s for s in filtered if not _has_item_ref(s)]


def _parse_response(raw: str) -> WorkflowPlan | ClarificationRequest:
    """Parse the planner's JSON response into a plan or clarification request."""
    extracted = _extract_json(raw)
    try:
        data = json.loads(extracted)
    except json.JSONDecodeError as exc:
        raise WorkflowPlanError(
            f"Planner returned non-JSON response: {exc}\nRaw output: {raw[:500]}",
            user_message="The planner model returned an invalid response. Try again.",
        ) from exc

    if not isinstance(data, dict):
        raise WorkflowPlanError(
            "Planner JSON root is not an object.",
            user_message="The planner returned an unexpected response format.",
        )

    if data.get("clarification_needed"):
        questions = data.get("questions", [])
        if not isinstance(questions, list):
            questions = [str(questions)]
        return ClarificationRequest(questions=[str(q) for q in questions])

    data = _repair_plan_data(data)

    # Build WorkflowPlan — use from_dict for consistency with the model
    try:
        plan = WorkflowPlan.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise WorkflowPlanError(
            f"Planner JSON is structurally invalid: {exc}",
            user_message="The planner returned a plan that could not be parsed.",
        ) from exc

    if not plan.stages:
        raise WorkflowPlanError(
            "Planner returned a plan with no stages.",
            user_message="The planner did not produce any pipeline stages.",
        )

    return plan


# ---------------------------------------------------------------------------
# WorkflowPlanner
# ---------------------------------------------------------------------------


class WorkflowPlanner:
    """Invokes an LLM to produce a :class:`WorkflowPlan` from a task description.

    The planner uses only the aliases and tools listed in the
    :class:`CapabilityManifest`. It never synthesises a final answer —
    its output is always a structured plan or a clarification request.
    """

    # Tags that indicate a model is suitable for planning tasks
    _PLANNER_TAGS: frozenset[str] = frozenset(["planning", "reasoning"])

    # Providers that run locally — avoid when possible to save API quota,
    # but they're fine as planners if that's all that's configured
    _LOCAL_PROVIDERS: frozenset[str] = frozenset(
        ["ollama", "lm_studio", "llamacpp", "lmstudio", "localai"]
    )

    def __init__(
        self,
        manifest: CapabilityManifest,
        model_registry: ModelRegistry,
        key_manager: KeyManager,
        provider_registry: ProviderRegistry,
        workflow_registry: WorkflowCapabilityRegistry | None = None,
    ) -> None:
        self._manifest = manifest
        self._model_registry = model_registry
        self._key_manager = key_manager
        self._provider_registry = provider_registry
        self._workflow_registry = workflow_registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def plan(
        self,
        task: str,
        planner_alias: str = "",
    ) -> WorkflowPlan | ClarificationRequest:
        """Generate a plan for *task*.

        *planner_alias* overrides the auto-selected planner model. When empty,
        the first alias with the 'planning' or 'reasoning' tag is used; if no
        tagged alias exists, the first alias in the registry is tried.
        """
        alias = self._resolve_alias(planner_alias)
        return await self._call_planner(task=task, extra_context="", alias=alias)

    async def plan_with_answers(
        self,
        task: str,
        clarification_answers: str,
        planner_alias: str = "",
    ) -> WorkflowPlan | ClarificationRequest:
        """Continue planning after the user answered clarification questions."""
        alias = self._resolve_alias(planner_alias)
        return await self._call_planner(
            task=task, extra_context=clarification_answers, alias=alias
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_alias(self, override: str) -> ModelAlias:
        if override:
            alias_obj = self._model_registry.get(override)
            if alias_obj is None:
                raise WorkflowPlanError(
                    f"Planner alias '{override}' not found in the model registry.",
                    user_message=f"No model alias named '{override}'. Add it with /model add.",
                )
            return alias_obj

        all_aliases = self._model_registry.list_all()
        if not all_aliases:
            raise WorkflowPlanError(
                "No model aliases configured — cannot run the planner.",
                user_message=(
                    "No models are configured. Add one with /model add, then retry."
                ),
            )

        def _tagged(aliases: list[ModelAlias]) -> list[ModelAlias]:
            if self._workflow_registry is None:
                return []
            return [
                a for a in aliases
                if self._PLANNER_TAGS & set(self._workflow_registry.get_tags(a.alias))
            ]

        local = [a for a in all_aliases if a.provider.lower() in self._LOCAL_PROVIDERS]
        cloud = [a for a in all_aliases if a.provider.lower() not in self._LOCAL_PROVIDERS]

        # 1. Local alias explicitly tagged for planning/reasoning — best choice.
        local_tagged = _tagged(local)
        if local_tagged:
            return local_tagged[0]

        # 2. Any local provider — avoids cloud API keys and quota limits.
        if local:
            return local[0]

        # 3. Cloud alias tagged for planning/reasoning — user configured it intentionally.
        cloud_tagged = _tagged(cloud)
        if cloud_tagged:
            return cloud_tagged[0]

        # 4. First alias regardless of provider.
        return all_aliases[0]

    # Rough character budget: most providers allow ~800k chars of input;
    # keeping the full prompt under this leaves room for the user's task.
    _MAX_PROMPT_CHARS: int = 60_000

    async def _call_planner(
        self,
        task: str,
        extra_context: str,
        alias: ModelAlias,
    ) -> WorkflowPlan | ClarificationRequest:
        manifest_text = self._manifest.load() or "(manifest not yet generated)"
        system_prompt = _build_system_prompt(manifest_text)

        if len(system_prompt) > self._MAX_PROMPT_CHARS:
            raise WorkflowPlanError(
                f"Planner system prompt is {len(system_prompt):,} chars "
                f"(limit {self._MAX_PROMPT_CHARS:,}). Run /workflow manifest refresh to rebuild.",
                user_message=(
                    "The capability manifest is too large for the planner model. "
                    "Run /workflow manifest refresh to rebuild a smaller version."
                ),
            )

        user_content = f"Task: {task}"
        if extra_context:
            user_content += f"\n\nClarification answers:\n{extra_context}"

        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ]

        api_key = self._key_manager.get_key(alias.provider)
        provider = self._provider_registry.instantiate(alias.provider, api_key=api_key)

        # 1024 tokens is ample for a plan JSON; using 4096 previously pushed
        # the combined input+output budget over Groq compound's per-request limit.
        gen_params = GenerationParams(temperature=0.2, max_tokens=1024)

        try:
            chunks: list[str] = []
            async for chunk in provider.stream_chat(
                messages=messages,
                model=alias.model_id,
                gen_params=gen_params,
            ):
                chunks.append(chunk.text)
            raw_response = "".join(chunks)
        except WorkflowPlanError:
            raise
        except Exception as exc:
            exc_detail = str(exc) or repr(exc)
            raise WorkflowPlanError(
                f"Provider '{alias.provider}' failed during planning: {exc_detail}",
                user_message=(
                    f"The planner model ({alias.alias}) returned an error: {exc_detail}"
                ),
            ) from exc

        return _parse_response(raw_response)

    # ------------------------------------------------------------------
    # Utility: build a plan from a raw JSON string (for saved workflows)
    # ------------------------------------------------------------------

    @staticmethod
    def parse_plan_json(json_text: str) -> WorkflowPlan:
        """Parse a raw JSON string directly into a WorkflowPlan (no LLM call)."""
        result = _parse_response(json_text)
        if isinstance(result, ClarificationRequest):
            raise WorkflowPlanError(
                "JSON text resolved to a clarification request, not a plan.",
                user_message="The provided JSON is a clarification request, not a plan.",
            )
        return result
