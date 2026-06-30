"""Tests for workflow/planner.py — WorkflowPlanner and JSON parsing."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.exceptions import WorkflowPlanError
from anythink.providers.base import StreamChunk
from anythink.workflow.models import ClarificationRequest, WorkflowPlan
from anythink.workflow.planner import (
    WorkflowPlanner,
    _extract_json,
    _parse_response,
)


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_bare_json(self) -> None:
        text = '{"key": "value"}'
        assert _extract_json(text) == '{"key": "value"}'

    def test_fenced_json_block(self) -> None:
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json(text)
        assert '"key"' in result

    def test_fenced_without_language(self) -> None:
        text = '```\n{"a": 1}\n```'
        assert '"a"' in _extract_json(text)

    def test_json_embedded_in_prose(self) -> None:
        text = 'Here is the plan: {"name": "test"} End.'
        result = _extract_json(text)
        assert '"name"' in result

    def test_no_json_returns_original(self) -> None:
        text = "no json here"
        assert _extract_json(text) == "no json here"


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

_VALID_PLAN_JSON = json.dumps(
    {
        "clarification_needed": False,
        "name": "email-summary",
        "trigger": "Read and summarize emails",
        "stages": [
            {
                "id": "stage_1",
                "type": "MCP_CALL",
                "label": "List inbox",
                "tool_name": "gmail.list_inbox",
                "tool_params": {"max_results": 10},
                "output_field": "email_list",
                "input_refs": [],
                "model_alias": "",
                "task_instruction": "",
                "expected_format": "",
                "condition_expr": "",
                "branch_a": [],
                "branch_b": [],
                "loop_def": None,
                "approval_message": "",
                "is_destructive": False,
                "is_parallel": False,
            }
        ],
        "models_used": [],
        "mcp_servers_used": ["gmail"],
        "estimated_duration_s": 60,
        "estimated_loop_iterations": None,
    }
)

_CLARIFICATION_JSON = json.dumps(
    {
        "clarification_needed": True,
        "questions": ["How many emails?", "Save to file?"],
    }
)


class TestParseResponse:
    def test_valid_plan(self) -> None:
        result = _parse_response(_VALID_PLAN_JSON)
        assert isinstance(result, WorkflowPlan)
        assert result.name == "email-summary"
        assert len(result.stages) == 1

    def test_clarification_request(self) -> None:
        result = _parse_response(_CLARIFICATION_JSON)
        assert isinstance(result, ClarificationRequest)
        assert len(result.questions) == 2

    def test_plan_wrapped_in_markdown(self) -> None:
        wrapped = f"Here's your plan:\n```json\n{_VALID_PLAN_JSON}\n```"
        result = _parse_response(wrapped)
        assert isinstance(result, WorkflowPlan)

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(WorkflowPlanError, match="non-JSON"):
            _parse_response("this is not json at all")

    def test_empty_stages_raises(self) -> None:
        data = json.loads(_VALID_PLAN_JSON)
        data["stages"] = []
        with pytest.raises(WorkflowPlanError, match="no stages"):
            _parse_response(json.dumps(data))

    def test_non_dict_root_raises(self) -> None:
        with pytest.raises(WorkflowPlanError):
            _parse_response("[1, 2, 3]")


# ---------------------------------------------------------------------------
# WorkflowPlanner
# ---------------------------------------------------------------------------


def _make_planner(response_text: str) -> tuple[WorkflowPlanner, MagicMock]:
    """Return a planner wired to a mock provider that yields *response_text*."""
    manifest = MagicMock()
    manifest.load.return_value = "[LOCAL MODELS]\n(none)\n"

    alias = MagicMock()
    alias.alias = "local-planner"
    alias.provider = "ollama"
    alias.model_id = "llama3:8b"

    model_reg = MagicMock()
    model_reg.get.return_value = alias
    model_reg.list_all.return_value = [alias]

    key_manager = MagicMock()
    key_manager.get_key.return_value = None

    # Build an async generator that yields chunks
    async def _fake_stream(*args, **kwargs):
        yield StreamChunk(text=response_text)

    provider = MagicMock()
    provider.stream_chat.return_value = _fake_stream()

    provider_reg = MagicMock()
    provider_reg.instantiate.return_value = provider

    planner = WorkflowPlanner(
        manifest=manifest,
        model_registry=model_reg,
        key_manager=key_manager,
        provider_registry=provider_reg,
    )
    return planner, provider


class TestWorkflowPlanner:
    @pytest.mark.asyncio
    async def test_plan_returns_workflow_plan(self) -> None:
        planner, _ = _make_planner(_VALID_PLAN_JSON)
        result = await planner.plan("Read and summarize emails", planner_alias="local-planner")
        assert isinstance(result, WorkflowPlan)
        assert result.name == "email-summary"

    @pytest.mark.asyncio
    async def test_plan_returns_clarification(self) -> None:
        planner, _ = _make_planner(_CLARIFICATION_JSON)
        result = await planner.plan("Ambiguous task")
        assert isinstance(result, ClarificationRequest)
        assert len(result.questions) == 2

    @pytest.mark.asyncio
    async def test_plan_with_answers(self) -> None:
        planner, _ = _make_planner(_VALID_PLAN_JSON)
        result = await planner.plan_with_answers(
            task="Read emails",
            clarification_answers="Last 10 emails. No file save.",
            planner_alias="local-planner",
        )
        assert isinstance(result, WorkflowPlan)

    @pytest.mark.asyncio
    async def test_no_aliases_raises(self) -> None:
        planner, _ = _make_planner(_VALID_PLAN_JSON)
        planner._model_registry.list_all.return_value = []
        with pytest.raises(WorkflowPlanError, match="No model"):
            await planner.plan("anything")

    @pytest.mark.asyncio
    async def test_unknown_alias_raises(self) -> None:
        planner, _ = _make_planner(_VALID_PLAN_JSON)
        planner._model_registry.get.return_value = None
        with pytest.raises(WorkflowPlanError, match="not found"):
            await planner.plan("anything", planner_alias="ghost-alias")

    def test_parse_plan_json_static(self) -> None:
        result = WorkflowPlanner.parse_plan_json(_VALID_PLAN_JSON)
        assert isinstance(result, WorkflowPlan)

    def test_parse_plan_json_clarification_raises(self) -> None:
        with pytest.raises(WorkflowPlanError):
            WorkflowPlanner.parse_plan_json(_CLARIFICATION_JSON)
