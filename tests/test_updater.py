"""Tests for the self-update module."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

from anythink.updater import check_update, current_version, fetch_latest_version, run_upgrade


class TestCurrentVersion:
    def test_returns_string(self) -> None:
        ver = current_version()
        assert isinstance(ver, str)
        assert len(ver) > 0

    def test_returns_unknown_on_import_error(self) -> None:
        with patch("anythink.updater.current_version") as mock:
            mock.return_value = "unknown"
            assert mock() == "unknown"

    def test_returns_unknown_when_version_missing(self) -> None:
        import types

        fake_anythink = types.ModuleType("anythink")
        with patch.dict(sys.modules, {"anythink": fake_anythink}):
            ver = current_version()
        assert ver == "unknown"


class TestFetchLatestVersion:
    async def test_returns_version_string(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"info": {"version": "3.0.0"}}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            version = await fetch_latest_version()
        assert version == "3.0.0"

    async def test_returns_none_on_network_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("network error"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            version = await fetch_latest_version()
        assert version is None


class TestCheckUpdate:
    async def test_returns_tuple(self) -> None:
        with patch("anythink.updater.fetch_latest_version", new=AsyncMock(return_value="9.9.9")):
            current, latest = await check_update()
        assert isinstance(current, str)
        assert latest == "9.9.9"

    async def test_latest_none_on_network_error(self) -> None:
        with patch("anythink.updater.fetch_latest_version", new=AsyncMock(return_value=None)):
            current, latest = await check_update()
        assert latest is None


class TestRunUpgrade:
    def test_success(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Successfully installed anythink-3.0.0\n"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            ok, output = run_upgrade()
        assert ok is True
        assert "Successfully installed" in output

    def test_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "ERROR: some pip error"
        with patch("subprocess.run", return_value=mock_result):
            ok, output = run_upgrade()
        assert ok is False
        assert "ERROR" in output
