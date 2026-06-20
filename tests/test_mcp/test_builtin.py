"""Tests for mcp/builtin/*.py servers."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from anythink.mcp.builtin.filesystem import FilesystemServer
from anythink.mcp.builtin.rag import RAGServer
from anythink.mcp.builtin.search import SearchServer
from anythink.mcp.builtin.sessions import SessionsServer

# ── Filesystem ────────────────────────────────────────────────────────────────


class TestFilesystemServer:
    def test_list_tools(self) -> None:
        srv = FilesystemServer()
        tools = srv.list_tools()
        names = {t.name for t in tools}
        assert "list_dir" in names
        assert "read_file" in names
        for t in tools:
            assert t.server_name == "filesystem"

    async def test_list_dir(self, tmp_path: Path) -> None:
        (tmp_path / "foo.txt").write_text("hello")
        (tmp_path / "subdir").mkdir()
        srv = FilesystemServer()
        result = await srv.call_tool("list_dir", {"path": str(tmp_path)})
        assert not result.is_error
        assert "foo.txt" in result.content
        assert "subdir" in result.content

    async def test_list_dir_missing(self, tmp_path: Path) -> None:
        srv = FilesystemServer()
        result = await srv.call_tool("list_dir", {"path": str(tmp_path / "nope")})
        assert result.is_error
        assert "not found" in result.content.lower()

    async def test_read_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        srv = FilesystemServer()
        result = await srv.call_tool("read_file", {"path": str(f)})
        assert not result.is_error
        assert "hello world" in result.content

    async def test_read_file_truncated(self, tmp_path: Path) -> None:
        f = tmp_path / "big.txt"
        f.write_text("A" * 100)
        srv = FilesystemServer()
        result = await srv.call_tool("read_file", {"path": str(f), "max_chars": 10})
        assert not result.is_error
        assert "truncated" in result.content

    async def test_read_file_not_found(self, tmp_path: Path) -> None:
        srv = FilesystemServer()
        result = await srv.call_tool("read_file", {"path": str(tmp_path / "nope.txt")})
        assert result.is_error

    async def test_unknown_tool(self) -> None:
        srv = FilesystemServer()
        result = await srv.call_tool("delete_everything", {})
        assert result.is_error


# ── Sessions ──────────────────────────────────────────────────────────────────


class TestSessionsServer:
    def _make_server(self) -> SessionsServer:
        mock_sm = MagicMock()
        mock_sm.list_sessions.return_value = []
        mock_sm.find_by_name_or_id.return_value = None
        return SessionsServer(mock_sm)

    def test_list_tools(self) -> None:
        srv = self._make_server()
        names = {t.name for t in srv.list_tools()}
        assert "list_sessions" in names
        assert "get_session" in names

    async def test_list_sessions_empty(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("list_sessions", {})
        assert not result.is_error
        assert "No saved sessions" in result.content

    async def test_list_sessions_with_data(self) -> None:
        mock_sm = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "abc123def456"
        mock_session.name = "Test Session"
        mock_session.messages = [MagicMock(), MagicMock()]
        mock_sm.list_sessions.return_value = [mock_session]
        srv = SessionsServer(mock_sm)

        result = await srv.call_tool("list_sessions", {})
        assert not result.is_error
        assert "abc123" in result.content
        assert "Test Session" in result.content

    async def test_get_session_not_found(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("get_session", {"id_or_name": "missing"})
        assert result.is_error
        assert "not found" in result.content.lower()

    async def test_get_session_found(self) -> None:
        mock_sm = MagicMock()
        mock_msg = MagicMock()
        mock_msg.role = "user"
        mock_msg.content = "Hello!"
        mock_session = MagicMock()
        mock_session.messages = [mock_msg]
        mock_sm.find_by_name_or_id.return_value = mock_session
        srv = SessionsServer(mock_sm)

        result = await srv.call_tool("get_session", {"id_or_name": "abc"})
        assert not result.is_error
        assert "Hello!" in result.content

    async def test_get_session_no_id(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("get_session", {})
        assert result.is_error


# ── RAG ───────────────────────────────────────────────────────────────────────


class TestRAGServer:
    def _make_server(self, is_active: bool = True) -> RAGServer:
        mock_rag = MagicMock()
        mock_rag.is_active = is_active
        mock_rag.retrieve = AsyncMock(return_value=[])
        mock_emb = MagicMock()
        return RAGServer(mock_rag, mock_emb)

    def test_list_tools(self) -> None:
        srv = self._make_server()
        names = {t.name for t in srv.list_tools()}
        assert "rag_search" in names

    async def test_rag_search_inactive(self) -> None:
        srv = self._make_server(is_active=False)
        result = await srv.call_tool("rag_search", {"query": "test"})
        assert result.is_error
        assert "No RAG index" in result.content

    async def test_rag_search_no_embedding(self) -> None:
        mock_rag = MagicMock()
        mock_rag.is_active = True
        srv = RAGServer(mock_rag, embedding_backend=None)
        result = await srv.call_tool("rag_search", {"query": "test"})
        assert result.is_error
        assert "embedding" in result.content.lower()

    async def test_rag_search_no_results(self) -> None:
        srv = self._make_server(is_active=True)
        result = await srv.call_tool("rag_search", {"query": "test"})
        assert not result.is_error
        assert "No results" in result.content

    async def test_rag_search_with_results(self) -> None:
        mock_rag = MagicMock()
        mock_rag.is_active = True
        mock_result = MagicMock()
        mock_result.source_path = "/some/file.py"
        mock_result.chunk_text = "def hello(): pass"
        mock_result.relevance = 0.95
        mock_rag.retrieve = AsyncMock(return_value=[mock_result])
        mock_emb = MagicMock()
        srv = RAGServer(mock_rag, mock_emb)

        result = await srv.call_tool("rag_search", {"query": "hello"})
        assert not result.is_error
        assert "file.py" in result.content
        assert "hello" in result.content

    async def test_unknown_tool(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("bad_tool", {})
        assert result.is_error


# ── Search ────────────────────────────────────────────────────────────────────


class TestSearchServer:
    def _make_server(self, has_backend: bool = True) -> SearchServer:
        mock_registry = MagicMock()
        if has_backend:
            mock_backend = MagicMock()
            mock_backend.search = AsyncMock(return_value=[])
            mock_registry.get_available.return_value = mock_backend
        else:
            mock_registry.get_available.return_value = None
        return SearchServer(mock_registry)

    def test_list_tools(self) -> None:
        srv = self._make_server()
        names = {t.name for t in srv.list_tools()}
        assert "web_search" in names

    async def test_search_no_backend(self) -> None:
        srv = self._make_server(has_backend=False)
        result = await srv.call_tool("web_search", {"query": "test"})
        assert result.is_error
        assert "No search backend" in result.content

    async def test_search_no_results(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("web_search", {"query": "test"})
        assert not result.is_error
        assert "No results" in result.content

    async def test_search_with_results(self) -> None:
        mock_registry = MagicMock()
        mock_result = MagicMock()
        mock_result.title = "Python docs"
        mock_result.url = "https://docs.python.org"
        mock_result.snippet = "Python is great."
        mock_backend = MagicMock()
        mock_backend.search = AsyncMock(return_value=[mock_result])
        mock_registry.get_available.return_value = mock_backend
        srv = SearchServer(mock_registry)

        result = await srv.call_tool("web_search", {"query": "python"})
        assert not result.is_error
        assert "Python docs" in result.content
        assert "docs.python.org" in result.content

    async def test_search_backend_exception(self) -> None:
        mock_registry = MagicMock()
        mock_backend = MagicMock()
        mock_backend.search = AsyncMock(side_effect=Exception("network error"))
        mock_registry.get_available.return_value = mock_backend
        srv = SearchServer(mock_registry)

        result = await srv.call_tool("web_search", {"query": "test"})
        assert result.is_error
        assert "Search failed" in result.content

    async def test_unknown_tool(self) -> None:
        srv = self._make_server()
        result = await srv.call_tool("bad_tool", {})
        assert result.is_error
