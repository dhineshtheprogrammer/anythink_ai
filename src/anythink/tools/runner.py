"""ToolRunner: approval-gated tool execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from anythink.tools.base import ApprovalMode, BaseTool, ToolResult


class ToolRunner:
    """Runs tools with configurable approval gating.

    In *ask* mode the caller must supply *ask_fn*; if omitted the tool runs
    automatically (useful for headless / non-TUI call sites).
    """

    def __init__(self, approval_mode: ApprovalMode = ApprovalMode.ASK) -> None:
        self.approval_mode = approval_mode

    async def run(
        self,
        tool: BaseTool,
        *,
        ask_fn: Callable[[str], Awaitable[bool]] | None = None,
        **kwargs: object,
    ) -> ToolResult:
        """Run *tool* with **kwargs**, prompting for approval if in ASK mode.

        Returns a ToolResult with ``approved=False`` when the user declined.
        Raises ``ToolExecutionError`` if the tool is unavailable.
        """
        if not tool.is_available():
            from anythink.exceptions import ToolExecutionError

            raise ToolExecutionError(
                f"Tool '{tool.name}' is not available in this environment.",
                user_message=(
                    f"Tool '{tool.name}' is not available. "
                    "Install the required runtime or package."
                ),
            )

        if self.approval_mode == ApprovalMode.ASK and ask_fn is not None:
            approved = await ask_fn(f"Run tool '{tool.name}'?")
            if not approved:
                return ToolResult(tool_name=tool.name, approved=False)

        return await tool.run(**kwargs)
