"""Tests for workflow/stages/ — each stage executor."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from anythink.workflow.models import (
    AccumulationStrategy,
    LoopDefinition,
    Stage,
    StageResult,
    StageType,
    UserDecision,
    WorkflowPlan,
    WorkflowState,
)

# ---------------------------------------------------------------------------
# Shared factories
# ---------------------------------------------------------------------------


def _make_plan(**kwargs: Any) -> WorkflowPlan:
    return WorkflowPlan(name=kwargs.get("name", "test"), trigger=kwargs.get("trigger", "test"))


def _make_state(**kwargs: Any) -> WorkflowState:
    plan = _make_plan()
    state = WorkflowState(plan=plan)
    state.accumulated_results.update(kwargs.get("accumulated", {}))
    for r in kwargs.get("completed", []):
        state.completed_stages.append(r)
    return state


def _make_stage(stage_type: StageType = StageType.MCP_CALL, **kwargs: Any) -> Stage:
    return Stage(
        id=kwargs.get("id", "stage_1"),
        type=stage_type,
        **{k: v for k, v in kwargs.items() if k != "id"},
    )


def _make_ctx(**overrides: Any) -> MagicMock:
    ctx = MagicMock()
    ctx.mcp_manager = MagicMock()
    ctx.model_registry = MagicMock()
    ctx.model_registry.list_all.return_value = []
    ctx.model_registry.get.return_value = None
    ctx.key_manager = MagicMock()
    ctx.key_manager.get_key.return_value = None
    ctx.provider_registry = MagicMock()
    ctx.spend_tracker = MagicMock()
    ctx.workflow_registry = MagicMock()
    ctx.workflow_registry.get_fallback_chain.return_value = []
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


def _make_callbacks(**overrides: Any) -> MagicMock:
    cb = MagicMock()
    cb.on_stage_start = AsyncMock()
    cb.on_stage_complete = AsyncMock()
    cb.on_approval_needed = AsyncMock(return_value="approved")
    cb.on_loop_progress = AsyncMock()
    cb.on_model_unavailable = AsyncMock(return_value="")
    for k, v in overrides.items():
        setattr(cb, k, v)
    return cb


# ---------------------------------------------------------------------------
# MCP_CALL executor
# ---------------------------------------------------------------------------


class TestMcpCallExecute:
    @pytest.mark.asyncio
    async def test_success_returns_stage_result(self) -> None:
        from anythink.mcp.models import MCPCallResult
        from anythink.workflow.stages.mcp_call import execute

        ctx = _make_ctx()
        mcp_result = MCPCallResult(
            tool_name="fs.read_file",
            server_name="fs",
            content="file contents",
            is_error=False,
        )
        ctx.mcp_manager.call_tool = AsyncMock(return_value=mcp_result)

        stage = _make_stage(StageType.MCP_CALL, tool_name="fs.read_file", output_field="file_data")
        state = _make_state()
        result = await execute(stage, state, ctx, _make_callbacks())

        assert isinstance(result, StageResult)
        assert result.stage_type == StageType.MCP_CALL
        assert result.tool_name == "fs.read_file"
        assert result.raw_content == "file contents"
        assert result.output["file_data"] == "file contents"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_error_result_sets_error_field(self) -> None:
        from anythink.mcp.models import MCPCallResult
        from anythink.workflow.stages.mcp_call import execute

        ctx = _make_ctx()
        ctx.mcp_manager.call_tool = AsyncMock(
            return_value=MCPCallResult(
                tool_name="fs.write_file",
                server_name="fs",
                content="Permission denied",
                is_error=True,
            )
        )

        stage = _make_stage(StageType.MCP_CALL, tool_name="fs.write_file")
        result = await execute(stage, _make_state(), ctx, _make_callbacks())

        assert result.error == "Permission denied"
        assert result.output == {}

    @pytest.mark.asyncio
    async def test_resolves_template_params(self) -> None:
        from anythink.mcp.models import MCPCallResult
        from anythink.workflow.stages.mcp_call import execute

        ctx = _make_ctx()
        ctx.mcp_manager.call_tool = AsyncMock(
            return_value=MCPCallResult(tool_name="fs.read_file", server_name="fs", content="ok")
        )

        stage = _make_stage(
            StageType.MCP_CALL,
            tool_name="fs.read_file",
            tool_params={"path": "{{stage_0.filepath}}"},
        )
        state = _make_state(accumulated={"stage_0.filepath": "/tmp/data.txt"})
        await execute(stage, state, ctx, _make_callbacks())

        _, call_kwargs = ctx.mcp_manager.call_tool.call_args
        # resolved_params is the second positional arg
        args = ctx.mcp_manager.call_tool.call_args.args
        assert args[1]["path"] == "/tmp/data.txt"

    @pytest.mark.asyncio
    async def test_no_output_field_uses_result_key(self) -> None:
        from anythink.mcp.models import MCPCallResult
        from anythink.workflow.stages.mcp_call import execute

        ctx = _make_ctx()
        ctx.mcp_manager.call_tool = AsyncMock(
            return_value=MCPCallResult(tool_name="t", server_name="s", content="x")
        )
        stage = _make_stage(StageType.MCP_CALL, tool_name="t", output_field="")
        result = await execute(stage, _make_state(), ctx, _make_callbacks())

        assert "result" in result.output


# ---------------------------------------------------------------------------
# LLM_SPECIALIST executor
# ---------------------------------------------------------------------------


class TestLlmSpecialistExecute:
    def _make_streaming_provider(self, text: str) -> MagicMock:
        from anythink.providers.base import StreamChunk, TokenUsage

        async def _stream(*args: Any, **kwargs: Any):
            yield StreamChunk(
                text=text,
                finish_reason="stop",
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )

        provider = MagicMock()
        provider.stream_chat.return_value = _stream()
        return provider

    @pytest.mark.asyncio
    async def test_success_returns_llm_result(self) -> None:
        from anythink.workflow.stages.llm_specialist import execute

        alias_obj = MagicMock()
        alias_obj.alias = "local-llm"
        alias_obj.provider = "ollama"
        alias_obj.model_id = "llama3:8b"

        ctx = _make_ctx()
        ctx.model_registry.get.return_value = alias_obj
        ctx.model_registry.list_all.return_value = [alias_obj]
        ctx.workflow_registry.get_fallback_chain.return_value = []
        ctx.provider_registry.instantiate.return_value = self._make_streaming_provider(
            "Summary here."
        )

        stage = _make_stage(
            StageType.LLM_SPECIALIST,
            model_alias="local-llm",
            task_instruction="Summarize this.",
            output_field="summary",
        )
        result = await execute(stage, _make_state(), ctx, _make_callbacks())

        assert result.stage_type == StageType.LLM_SPECIALIST
        assert result.model_alias == "local-llm"
        assert result.raw_content == "Summary here."
        assert result.output["summary"] == "Summary here."
        assert result.error is None
        assert result.fallback_used is False

    @pytest.mark.asyncio
    async def test_fallback_on_provider_error(self) -> None:
        from anythink.workflow.stages.llm_specialist import execute

        primary = MagicMock()
        primary.alias = "primary"
        primary.provider = "openai"
        primary.model_id = "gpt-4o"

        fallback = MagicMock()
        fallback.alias = "fallback"
        fallback.provider = "ollama"
        fallback.model_id = "llama3:8b"

        ctx = _make_ctx()
        ctx.workflow_registry.get_fallback_chain.return_value = ["fallback"]
        ctx.model_registry.get.side_effect = lambda alias: {
            "primary": primary,
            "fallback": fallback,
        }.get(alias)

        # Primary raises, fallback returns good response
        async def _fail(*a: Any, **kw: Any):
            raise RuntimeError("connection refused")
            yield  # make it a generator

        async def _ok(*a: Any, **kw: Any):
            from anythink.providers.base import StreamChunk

            yield StreamChunk(text="ok from fallback")

        provider_primary = MagicMock()
        provider_primary.stream_chat.return_value = _fail()
        provider_fallback = MagicMock()
        provider_fallback.stream_chat.return_value = _ok()

        ctx.provider_registry.instantiate.side_effect = lambda p, **kw: (
            provider_primary if p == "openai" else provider_fallback
        )

        stage = _make_stage(StageType.LLM_SPECIALIST, model_alias="primary")
        result = await execute(stage, _make_state(), ctx, _make_callbacks())

        assert result.error is None
        assert result.model_alias == "fallback"
        assert result.fallback_used is True

    @pytest.mark.asyncio
    async def test_all_candidates_exhausted_returns_error(self) -> None:
        from anythink.workflow.stages.llm_specialist import execute

        ctx = _make_ctx()
        ctx.model_registry.get.return_value = None
        ctx.model_registry.list_all.return_value = []
        ctx.workflow_registry.get_fallback_chain.return_value = []

        stage = _make_stage(StageType.LLM_SPECIALIST, model_alias="ghost")
        result = await execute(stage, _make_state(), ctx, _make_callbacks())

        assert result.error is not None

    @pytest.mark.asyncio
    async def test_records_spend_when_usage_available(self) -> None:
        from anythink.workflow.stages.llm_specialist import execute

        alias_obj = MagicMock()
        alias_obj.alias = "m"
        alias_obj.provider = "ollama"
        alias_obj.model_id = "llama3"

        ctx = _make_ctx()
        ctx.model_registry.get.return_value = alias_obj
        ctx.model_registry.list_all.return_value = [alias_obj]
        ctx.workflow_registry.get_fallback_chain.return_value = []
        ctx.provider_registry.instantiate.return_value = self._make_streaming_provider("done")

        stage = _make_stage(StageType.LLM_SPECIALIST, model_alias="m")
        await execute(stage, _make_state(), ctx, _make_callbacks())

        ctx.spend_tracker.record.assert_called_once()


# ---------------------------------------------------------------------------
# USER_APPROVAL executor
# ---------------------------------------------------------------------------


class TestUserApprovalExecute:
    @pytest.mark.asyncio
    async def test_approved(self) -> None:
        from anythink.workflow.stages.user_approval import execute

        callbacks = _make_callbacks()
        callbacks.on_approval_needed = AsyncMock(return_value="approved")

        stage = _make_stage(StageType.USER_APPROVAL, approval_message="Delete file?")
        result = await execute(stage, _make_state(), _make_ctx(), callbacks)

        assert result.user_decision == UserDecision.APPROVED
        assert result.skipped is False
        assert result.output["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_skipped(self) -> None:
        from anythink.workflow.stages.user_approval import execute

        callbacks = _make_callbacks()
        callbacks.on_approval_needed = AsyncMock(return_value="skipped")

        stage = _make_stage(StageType.USER_APPROVAL)
        result = await execute(stage, _make_state(), _make_ctx(), callbacks)

        assert result.user_decision == UserDecision.SKIPPED
        assert result.skipped is True

    @pytest.mark.asyncio
    async def test_aborted(self) -> None:
        from anythink.workflow.stages.user_approval import execute

        callbacks = _make_callbacks()
        callbacks.on_approval_needed = AsyncMock(return_value="aborted")

        stage = _make_stage(StageType.USER_APPROVAL)
        result = await execute(stage, _make_state(), _make_ctx(), callbacks)

        assert result.user_decision == UserDecision.ABORTED

    @pytest.mark.asyncio
    async def test_invalid_decision_defaults_to_approved(self) -> None:
        from anythink.workflow.stages.user_approval import execute

        callbacks = _make_callbacks()
        callbacks.on_approval_needed = AsyncMock(return_value="yes_please")

        stage = _make_stage(StageType.USER_APPROVAL)
        result = await execute(stage, _make_state(), _make_ctx(), callbacks)

        assert result.user_decision == UserDecision.APPROVED

    @pytest.mark.asyncio
    async def test_default_message_used_when_empty(self) -> None:
        from anythink.workflow.stages.user_approval import execute

        callbacks = _make_callbacks()
        callbacks.on_approval_needed = AsyncMock(return_value="approved")

        stage = _make_stage(StageType.USER_APPROVAL, approval_message="")
        await execute(stage, _make_state(), _make_ctx(), callbacks)

        call_args = callbacks.on_approval_needed.call_args.args[0]
        assert len(call_args) > 0


# ---------------------------------------------------------------------------
# CONDITION executor
# ---------------------------------------------------------------------------


class TestConditionExecute:
    @pytest.mark.asyncio
    async def test_true_expression_returns_branch_a(self) -> None:
        from anythink.workflow.stages.condition import execute

        stage = _make_stage(StageType.CONDITION, condition_expr="1 == 1")
        result = await execute(stage, _make_state(), _make_ctx(), _make_callbacks())

        assert result.output["branch"] == "a"
        assert result.output["condition_result"] is True

    @pytest.mark.asyncio
    async def test_false_expression_returns_branch_b(self) -> None:
        from anythink.workflow.stages.condition import execute

        stage = _make_stage(StageType.CONDITION, condition_expr="1 == 2")
        result = await execute(stage, _make_state(), _make_ctx(), _make_callbacks())

        assert result.output["branch"] == "b"
        assert result.output["condition_result"] is False

    @pytest.mark.asyncio
    async def test_dot_path_ref_resolved(self) -> None:
        from anythink.workflow.stages.condition import execute

        state = _make_state(accumulated={"stage_1.count": 5})
        stage = _make_stage(StageType.CONDITION, condition_expr="stage_1.count > 3")
        result = await execute(stage, state, _make_ctx(), _make_callbacks())

        assert result.output["branch"] == "a"

    @pytest.mark.asyncio
    async def test_invalid_expression_defaults_to_branch_b(self) -> None:
        from anythink.workflow.stages.condition import execute

        stage = _make_stage(StageType.CONDITION, condition_expr="this is >>>invalid<<<")
        result = await execute(stage, _make_state(), _make_ctx(), _make_callbacks())

        assert result.output["branch"] == "b"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_string_comparison(self) -> None:
        from anythink.workflow.stages.condition import execute

        state = _make_state(accumulated={"stage_1.status": "done"})
        stage = _make_stage(StageType.CONDITION, condition_expr="stage_1.status == 'done'")
        result = await execute(stage, state, _make_ctx(), _make_callbacks())

        assert result.output["branch"] == "a"


# ---------------------------------------------------------------------------
# FORMATTER executor
# ---------------------------------------------------------------------------


class TestFormatterExecute:
    @pytest.mark.asyncio
    async def test_plain_text_strips_markdown(self) -> None:
        from anythink.workflow.stages.formatter import execute

        state = _make_state()
        state.completed_stages.append(
            StageResult(
                stage_id="s0", stage_type=StageType.LLM_SPECIALIST, raw_content="**bold** text"
            )
        )
        stage = _make_stage(StageType.FORMATTER, expected_format="plain_text")
        result = await execute(stage, state, _make_ctx(), _make_callbacks())

        assert "**" not in result.raw_content
        assert "bold" in result.raw_content

    @pytest.mark.asyncio
    async def test_json_wraps_non_json(self) -> None:
        from anythink.workflow.stages.formatter import execute

        state = _make_state()
        state.completed_stages.append(
            StageResult(
                stage_id="s0", stage_type=StageType.LLM_SPECIALIST, raw_content="hello world"
            )
        )
        stage = _make_stage(StageType.FORMATTER, expected_format="json")
        result = await execute(stage, state, _make_ctx(), _make_callbacks())

        data = json.loads(result.raw_content)
        assert "content" in data

    @pytest.mark.asyncio
    async def test_numbered_list_numbers_lines(self) -> None:
        from anythink.workflow.stages.formatter import execute

        state = _make_state()
        state.completed_stages.append(
            StageResult(
                stage_id="s0",
                stage_type=StageType.LLM_SPECIALIST,
                raw_content="apple\nbanana\ncherry",
            )
        )
        stage = _make_stage(StageType.FORMATTER, expected_format="numbered_list")
        result = await execute(stage, state, _make_ctx(), _make_callbacks())

        assert result.raw_content.startswith("1.")
        assert "2." in result.raw_content
        assert "3." in result.raw_content

    @pytest.mark.asyncio
    async def test_html_wraps_paragraphs(self) -> None:
        from anythink.workflow.stages.formatter import execute

        state = _make_state()
        state.completed_stages.append(
            StageResult(stage_id="s0", stage_type=StageType.LLM_SPECIALIST, raw_content="Hello")
        )
        stage = _make_stage(StageType.FORMATTER, expected_format="html")
        result = await execute(stage, state, _make_ctx(), _make_callbacks())

        assert "<p>" in result.raw_content

    @pytest.mark.asyncio
    async def test_input_refs_take_priority(self) -> None:
        from anythink.workflow.stages.formatter import execute

        state = _make_state(accumulated={"stage_0.text": "from ref"})
        state.completed_stages.append(
            StageResult(stage_id="s0", stage_type=StageType.LLM_SPECIALIST, raw_content="from raw")
        )
        stage = _make_stage(
            StageType.FORMATTER,
            expected_format="plain_text",
            input_refs=["stage_0.text"],
        )
        result = await execute(stage, state, _make_ctx(), _make_callbacks())

        assert "from ref" in result.raw_content

    @pytest.mark.asyncio
    async def test_output_field_stored_correctly(self) -> None:
        from anythink.workflow.stages.formatter import execute

        state = _make_state()
        state.completed_stages.append(
            StageResult(stage_id="s0", stage_type=StageType.LLM_SPECIALIST, raw_content="x")
        )
        stage = _make_stage(StageType.FORMATTER, expected_format="plain_text", output_field="out")
        result = await execute(stage, state, _make_ctx(), _make_callbacks())

        assert "out" in result.output


# ---------------------------------------------------------------------------
# _safe_eval unit tests
# ---------------------------------------------------------------------------


class TestSafeEval:
    def test_numeric_comparison(self) -> None:
        from anythink.workflow.stages.condition import _safe_eval

        assert _safe_eval("5 > 3", {}) is True
        assert _safe_eval("5 < 3", {}) is False

    def test_boolean_operators(self) -> None:
        from anythink.workflow.stages.condition import _safe_eval

        assert _safe_eval("True and True", {}) is True
        assert _safe_eval("True and False", {}) is False
        assert _safe_eval("False or True", {}) is True

    def test_not_operator(self) -> None:
        from anythink.workflow.stages.condition import _safe_eval

        assert _safe_eval("not False", {}) is True

    def test_context_lookup(self) -> None:
        from anythink.workflow.stages.condition import _safe_eval

        assert _safe_eval("x == 42", {"x": 42}) is True

    def test_dot_path_lookup(self) -> None:
        from anythink.workflow.stages.condition import _safe_eval

        assert _safe_eval("stage_1.count > 0", {"stage_1.count": 5}) is True

    def test_in_operator(self) -> None:
        from anythink.workflow.stages.condition import _safe_eval

        assert _safe_eval("'a' in items", {"items": ["a", "b"]}) is True

    def test_string_equality(self) -> None:
        from anythink.workflow.stages.condition import _safe_eval

        assert _safe_eval("status == 'done'", {"status": "done"}) is True

    def test_none_lookup_returns_none(self) -> None:
        from anythink.workflow.stages.condition import _safe_eval

        # A missing ref evaluates to None, and None == None is True
        assert _safe_eval("missing == None", {}) is True


# ---------------------------------------------------------------------------
# _resolve_params unit test
# ---------------------------------------------------------------------------


class TestResolveMcpParams:
    def test_resolves_template_placeholder(self) -> None:
        from anythink.workflow.stages.mcp_call import _resolve_params

        state = _make_state(accumulated={"stage_0.path": "/data/file.txt"})
        params = {"path": "{{stage_0.path}}", "mode": "read"}
        resolved = _resolve_params(params, state)

        assert resolved["path"] == "/data/file.txt"
        assert resolved["mode"] == "read"

    def test_unresolved_placeholder_kept_as_is(self) -> None:
        from anythink.workflow.stages.mcp_call import _resolve_params

        state = _make_state()
        params = {"path": "{{stage_0.missing}}"}
        resolved = _resolve_params(params, state)

        assert resolved["path"] == "{{stage_0.missing}}"
