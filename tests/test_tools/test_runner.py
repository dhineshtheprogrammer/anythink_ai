"""Tests for tools/runner.py."""

from __future__ import annotations

import pytest

from anythink.tools.base import ApprovalMode, BaseTool, ToolResult
from anythink.tools.runner import ToolRunner


class _AlwaysAvailable(BaseTool):
    name = "ok_tool"
    description = "Always available."

    async def run(self, **kwargs: object) -> ToolResult:
        return ToolResult(tool_name=self.name, stdout="done")


class _NeverAvailable(BaseTool):
    name = "broken_tool"
    description = "Never available."

    def is_available(self) -> bool:
        return False

    async def run(self, **kwargs: object) -> ToolResult:  # pragma: no cover
        return ToolResult(tool_name=self.name)


class TestToolRunnerAutoMode:
    async def test_auto_runs_without_ask_fn(self) -> None:
        runner = ToolRunner(ApprovalMode.AUTO)
        result = await runner.run(_AlwaysAvailable())
        assert result.approved
        assert result.stdout == "done"

    async def test_auto_ignores_ask_fn(self) -> None:
        called: list[bool] = []

        async def ask_fn(msg: str) -> bool:
            called.append(True)
            return True

        runner = ToolRunner(ApprovalMode.AUTO)
        result = await runner.run(_AlwaysAvailable(), ask_fn=ask_fn)
        assert result.approved
        assert not called  # ask_fn never called in AUTO mode


class TestToolRunnerAskMode:
    async def test_ask_approved(self) -> None:
        async def ask_fn(msg: str) -> bool:
            return True

        runner = ToolRunner(ApprovalMode.ASK)
        result = await runner.run(_AlwaysAvailable(), ask_fn=ask_fn)
        assert result.approved
        assert result.stdout == "done"

    async def test_ask_denied(self) -> None:
        async def ask_fn(msg: str) -> bool:
            return False

        runner = ToolRunner(ApprovalMode.ASK)
        result = await runner.run(_AlwaysAvailable(), ask_fn=ask_fn)
        assert not result.approved
        assert result.stdout == ""

    async def test_ask_without_ask_fn_runs_automatically(self) -> None:
        runner = ToolRunner(ApprovalMode.ASK)
        result = await runner.run(_AlwaysAvailable())
        assert result.approved


class TestToolRunnerUnavailable:
    async def test_raises_on_unavailable_tool(self) -> None:
        from anythink.exceptions import ToolExecutionError

        runner = ToolRunner(ApprovalMode.AUTO)
        with pytest.raises(ToolExecutionError, match="not available"):
            await runner.run(_NeverAvailable())
