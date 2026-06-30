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
- Use a LOOP stage when the task involves processing each item in a collection
  individually (e.g., each email, each file).
- Use parallel branches when sub-tasks are independent of each other.
- If the task is ambiguous in a way that would produce significantly different
  plans, output a clarification request instead of a plan.
- Never synthesise a final answer yourself — only produce a plan.
"""

_OUTPUT_SCHEMA = """\
OUTPUT FORMAT — respond with ONLY valid JSON in one of these two shapes:

Shape 1 — Clarification needed:
{
  "clarification_needed": true,
  "questions": ["Question 1?", "Question 2?"]
}

Shape 2 — Full plan:
{
  "clarification_needed": false,
  "name": "short-workflow-name",
  "trigger": "<original task>",
  "stages": [
    {
      "id": "stage_1",
      "type": "MCP_CALL|LLM_SPECIALIST|USER_APPROVAL|CONDITION|FORMATTER|LOOP",
      "label": "Human-readable label",
      "model_alias": "",
      "task_instruction": "",
      "tool_name": "server.tool_name",
      "tool_params": {},
      "output_field": "field_name",
      "input_refs": ["stage_N.field"],
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
  "models_used": ["alias1"],
  "mcp_servers_used": ["server1"],
  "estimated_duration_s": null,
  "estimated_loop_iterations": null
}

For LOOP stages, set loop_def to:
{
  "input_collection_ref": "stage_N.field_name",
  "sub_stages": [ <same stage objects> ],
  "accumulation_strategy": "append"
}

Omit irrelevant fields by setting them to empty string, empty list, or null.
Respond with ONLY the JSON — no explanation, no markdown, no code fences.
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

    def __init__(
        self,
        manifest: CapabilityManifest,
        model_registry: ModelRegistry,
        key_manager: KeyManager,
        provider_registry: ProviderRegistry,
    ) -> None:
        self._manifest = manifest
        self._model_registry = model_registry
        self._key_manager = key_manager
        self._provider_registry = provider_registry

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
        return all_aliases[0]

    async def _call_planner(
        self,
        task: str,
        extra_context: str,
        alias: ModelAlias,
    ) -> WorkflowPlan | ClarificationRequest:
        manifest_text = self._manifest.load() or "(manifest not yet generated)"
        system_prompt = _build_system_prompt(manifest_text)

        user_content = f"Task: {task}"
        if extra_context:
            user_content += f"\n\nClarification answers:\n{extra_context}"

        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ]

        api_key = self._key_manager.get_key(alias.provider)
        provider = self._provider_registry.instantiate(alias.provider, api_key=api_key)

        gen_params = GenerationParams(temperature=0.2, max_tokens=4096)

        chunks: list[str] = []
        async for chunk in provider.stream_chat(
            messages=messages,
            model=alias.model_id,
            gen_params=gen_params,
        ):
            chunks.append(chunk.text)

        raw_response = "".join(chunks)
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
