"""Tool framework: base types for the tool-call abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class ApprovalMode(StrEnum):
    ASK = "ask"
    AUTO = "auto"


@dataclass
class ToolResult:
    """Outcome of running a tool."""

    tool_name: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_s: float = 0.0
    approved: bool = True

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


class BaseTool(ABC):
    """Abstract base for all Anythink tools (exec, browse, MCP, …)."""

    name: str = ""
    description: str = ""

    @abstractmethod
    async def run(self, **kwargs: object) -> ToolResult:
        """Execute the tool and return a ToolResult."""

    def is_available(self) -> bool:
        """Return True when this tool can run in the current environment."""
        return True
