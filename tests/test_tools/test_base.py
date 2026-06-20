"""Tests for tools/base.py."""

from __future__ import annotations

import pytest

from anythink.tools.base import ApprovalMode, BaseTool, ToolResult


class TestToolResult:
    def test_succeeded_on_zero_exit(self) -> None:
        r = ToolResult(tool_name="t", exit_code=0)
        assert r.succeeded

    def test_failed_on_nonzero_exit(self) -> None:
        r = ToolResult(tool_name="t", exit_code=1)
        assert not r.succeeded

    def test_defaults(self) -> None:
        r = ToolResult(tool_name="my_tool")
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.duration_s == 0.0
        assert r.approved is True


class TestApprovalMode:
    def test_from_string(self) -> None:
        assert ApprovalMode("ask") == ApprovalMode.ASK
        assert ApprovalMode("auto") == ApprovalMode.AUTO

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            ApprovalMode("invalid")


class ConcreteTestTool(BaseTool):
    name = "test_tool"
    description = "A test tool."

    async def run(self, **kwargs: object) -> ToolResult:
        return ToolResult(tool_name=self.name)


class TestBaseTool:
    def test_is_available_default_true(self) -> None:
        assert ConcreteTestTool().is_available()

    async def test_run_returns_result(self) -> None:
        tool = ConcreteTestTool()
        result = await tool.run()
        assert result.tool_name == "test_tool"
