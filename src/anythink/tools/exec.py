"""Code execution tool: runs user code via PATH runtimes.

Design trade-off (bandit B603): code execution is the *explicit purpose* of
this module. The runtime binary is always resolved via ``shutil.which`` (no
partial paths), ``shell=False`` is the asyncio default, and user code runs
only after an optional approval prompt (see ``ApprovalMode``). There is no
remote-code path; the user pastes code they wrote themselves.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import time
from pathlib import Path

from anythink.exceptions import ToolExecutionError
from anythink.tools.base import BaseTool, ToolResult

# Language alias → PATH executable name.
RUNTIMES: dict[str, str] = {
    "python": "python3",
    "python3": "python3",
    "bash": "bash",
    "sh": "sh",
    "shell": "bash",
    "javascript": "node",
    "js": "node",
    "node": "node",
    "ruby": "ruby",
    "rb": "ruby",
    "go": "go",
    "sql": "sqlite3",
}

_SUFFIXES: dict[str, str] = {
    "python": ".py",
    "python3": ".py",
    "bash": ".sh",
    "sh": ".sh",
    "shell": ".sh",
    "javascript": ".js",
    "js": ".js",
    "node": ".js",
    "ruby": ".rb",
    "rb": ".rb",
    "go": ".go",
    "sql": ".sql",
}

TIMEOUT_SECONDS: int = 30


def find_runtime(language: str) -> str | None:
    """Return the resolved absolute path for *language*'s runtime, or None."""
    exe = RUNTIMES.get(language.lower())
    if exe is None:
        return None
    return shutil.which(exe)


class CodeExecTool(BaseTool):
    """Execute code snippets via the user's local PATH runtimes."""

    name = "code_exec"
    description = "Run code in the user's environment via PATH runtimes (python3, bash, node, …)."

    def is_available(self) -> bool:
        return any(shutil.which(exe) for exe in set(RUNTIMES.values()))

    async def run(  # type: ignore[override]
        self,
        *,
        language: str = "python",
        code: str = "",
    ) -> ToolResult:
        """Execute *code* with the runtime for *language*."""
        runtime = find_runtime(language)
        if runtime is None:
            raise ToolExecutionError(
                f"Runtime for '{language}' not found on PATH.",
                user_message=(
                    f"No runtime for '{language}' found on PATH. "
                    "Install it and add it to your PATH."
                ),
            )

        suffix = _SUFFIXES.get(language.lower(), ".tmp")
        t0 = time.monotonic()

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            delete=False,
            encoding="utf-8",
        ) as fp:
            fp.write(code)
            tmp_path = fp.name

        try:
            # nosec B603 — runtime resolved via shutil.which; shell=False (asyncio default);
            # code is user-supplied and runs only in their own environment.
            proc = await asyncio.create_subprocess_exec(  # nosec B603
                runtime,
                tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=float(TIMEOUT_SECONDS),
                )
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                raise ToolExecutionError(
                    f"Code execution timed out after {TIMEOUT_SECONDS}s.",
                    user_message=f"Execution timed out after {TIMEOUT_SECONDS} seconds.",
                ) from None
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return ToolResult(
            tool_name=self.name,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            exit_code=proc.returncode or 0,
            duration_s=round(time.monotonic() - t0, 3),
        )
