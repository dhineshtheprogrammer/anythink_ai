"""Tests for tools/exec.py."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anythink.exceptions import ToolExecutionError
from anythink.tools.exec import RUNTIMES, CodeExecTool, find_runtime


class TestFindRuntime:
    def test_known_language_resolves(self) -> None:
        with patch("anythink.tools.exec.shutil.which", return_value="/usr/bin/python3"):
            assert find_runtime("python") == "/usr/bin/python3"

    def test_alias_resolves(self) -> None:
        with patch("anythink.tools.exec.shutil.which", return_value="/usr/bin/node"):
            assert find_runtime("js") == "/usr/bin/node"

    def test_unknown_language_returns_none(self) -> None:
        assert find_runtime("cobol") is None

    def test_missing_from_path_returns_none(self) -> None:
        with patch("anythink.tools.exec.shutil.which", return_value=None):
            assert find_runtime("python") is None


class TestCodeExecToolAvailability:
    def test_available_when_runtime_found(self) -> None:
        with patch("anythink.tools.exec.shutil.which", return_value="/usr/bin/python3"):
            assert CodeExecTool().is_available()

    def test_unavailable_when_no_runtime(self) -> None:
        with patch("anythink.tools.exec.shutil.which", return_value=None):
            assert not CodeExecTool().is_available()


class TestCodeExecToolRun:
    async def test_happy_path_returns_stdout(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"hello\n", b""))

        with (
            patch("anythink.tools.exec.shutil.which", return_value="/usr/bin/python3"),
            patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)),
        ):
            result = await CodeExecTool().run(language="python", code="print('hello')")

        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.tool_name == "code_exec"
        assert result.succeeded

    async def test_nonzero_exit_sets_failed(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"NameError\n"))

        with (
            patch("anythink.tools.exec.shutil.which", return_value="/usr/bin/python3"),
            patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)),
        ):
            result = await CodeExecTool().run(language="python", code="bad code")

        assert result.exit_code == 1
        assert not result.succeeded
        assert "NameError" in result.stderr

    async def test_missing_runtime_raises(self) -> None:
        with patch("anythink.tools.exec.shutil.which", return_value=None):
            with pytest.raises(ToolExecutionError, match="not found"):
                await CodeExecTool().run(language="python", code="print('hi')")

    async def test_unknown_language_raises(self) -> None:
        with pytest.raises(ToolExecutionError, match="not found"):
            await CodeExecTool().run(language="cobol", code="DISPLAY 'hi'")

    async def test_timeout_raises(self) -> None:
        mock_proc = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch("anythink.tools.exec.shutil.which", return_value="/usr/bin/python3"),
            patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)),
            patch("asyncio.wait_for", side_effect=TimeoutError),
        ):
            with pytest.raises(ToolExecutionError, match="timed out"):
                await CodeExecTool().run(language="python", code="import time; time.sleep(999)")

        mock_proc.kill.assert_called_once()

    async def test_duration_is_recorded(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))

        with (
            patch("anythink.tools.exec.shutil.which", return_value="/usr/bin/python3"),
            patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)),
        ):
            result = await CodeExecTool().run(language="python", code="pass")

        assert result.duration_s >= 0.0

    def test_runtimes_dict_non_empty(self) -> None:
        assert len(RUNTIMES) > 0
        assert "python" in RUNTIMES
        assert "bash" in RUNTIMES
